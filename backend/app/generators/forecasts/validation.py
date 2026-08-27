from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.core.ids import deterministic_uuid
from app.domain.forecasts import ForecastWindowSelector, daily_final_versions, forecast_anchor, thirteen_week_totals, week_one_start
from app.generators.evidence_foundation.calendar import add_months, days
from app.generators.evidence_foundation.validation import matches_shape, shape_metrics
from app.generators.evidence_foundation.world import DemandObservationIndex
from app.generators.forecasts.generator import stored_months
from app.models.platform.forecasts import FORECAST_MODELS


class ForecastValidationError(ValueError):
    pass


class ForecastValidator:
    def validate(self, world, master, procurement, scenario, evidence, dataset_id, dataset_signature, snapshot, config, sc):
        def require(condition, message):
            if not condition:
                raise ForecastValidationError(message)

        references = defaultdict(set)
        records = list(master.all_records())
        for name in evidence.COLLECTION_NAMES:
            records.extend(getattr(evidence, name))
        for model in FORECAST_MODELS:
            rows = getattr(world, model.__tablename__)
            require(bool(rows), 'INCOMPLETE_FORECAST_WORLD')
            records.extend(rows)
        for row in records:
            references[row.__table__.fullname].add(tuple(getattr(row, c.key) for c in row.__table__.primary_key))
        references['platform.dataset_versions'] = {(dataset_id,)}
        forbidden = {'scenario_pattern', 'true_cause', 'demand_change_type', 'causal_project_id', 'expected_action'}
        for model in FORECAST_MODELS:
            require(not forbidden.intersection(model.__table__.columns.keys()), 'FORECAST_TRUTH_LEAKAGE')
            rows = getattr(world, model.__tablename__)
            for constraint in [model.__table__.primary_key] + [c for c in model.__table__.constraints if isinstance(c, UniqueConstraint)]:
                keys = [tuple(getattr(r, c.key) for c in constraint.columns) for r in rows]
                require(len(keys) == len(set(keys)), 'DUPLICATE_FORECAST_FACT')
            fks = [c for c in model.__table__.constraints if isinstance(c, ForeignKeyConstraint)]
            for row in rows:
                require(row.dataset_version_id == dataset_id, 'CROSS_DATASET_FORECAST')
                for fk in fks:
                    local = tuple(getattr(row, item.parent.key) for item in fk.elements)
                    require(local in references[fk.elements[0].column.table.fullname], 'INVALID_FORECAST_FK')

        history = min(r.demand_date for r in evidence.demand_signal_points)
        dates = sorted({v.version_date for v in world.forecast_versions})
        require(dates == list(days(week_one_start(history), snapshot))[::7], 'INVALID_SHARED_VERSION_CALENDAR')
        for version in world.forecast_versions:
            require(version.sequence_no > 0 and type(version.is_valid) is bool, 'INVALID_FORECAST_VERSION')
            require(version.forecast_version_id == deterministic_uuid(dataset_signature, 'forecast_version', f'{version.version_date}:{version.sequence_no}'), 'UNSTABLE_FORECAST_VERSION_ID')
        final = daily_final_versions(world.forecast_versions, dataset_id)
        require(bool(final), 'NO_VALID_FORECAST_VERSION')
        latest = final[-1]
        require(len(world.weekly_forecast_snapshots) == 1 and world.weekly_forecast_snapshots[0].is_latest, 'INVALID_LATEST_WEEKLY_SNAPSHOT')
        weekly_snapshot = world.weekly_forecast_snapshots[0]
        require(weekly_snapshot.snapshot_date == snapshot and weekly_snapshot.source_forecast_version_id == latest.forecast_version_id, 'INVALID_WEEKLY_SNAPSHOT_LINEAGE')
        signals = {r.demand_signal_id: r for r in evidence.demand_signals}
        pairs = {(r.material_id, r.project_id): r for r in evidence.demand_signals}
        materials = {r.material_id: r for r in master.materials}
        versions = {r.forecast_version_id: r for r in world.forecast_versions}
        source = DemandObservationIndex(evidence)

        @lru_cache(maxsize=None)
        def observed_months(signal_id, date):
            result = defaultdict(Decimal)
            for day, qty in source.observe(signal_id, date).items():
                result[day.replace(day=1)] += qty
            return result

        monthly = defaultdict(dict)
        for row in world.monthly_forecasts:
            signal = signals[row.demand_signal_id]
            require((row.material_id, row.project_id) == (signal.material_id, signal.project_id), 'INVALID_DEMAND_LINEAGE')
            require(row.forecast_month.day == 1 and row.forecast_qty >= 0 and row.forecast_source == config.forecast_source, 'INVALID_MONTHLY_FORECAST')
            version = versions[row.forecast_version_id]
            require(row.forecast_qty == observed_months(row.demand_signal_id, version.version_date)[row.forecast_month], 'MONTHLY_SOURCE_RECONCILIATION')
            monthly[(row.forecast_version_id, row.material_id, row.project_id)][row.forecast_month] = row.forecast_qty
        require(set(monthly) == {(v.forecast_version_id, m, p) for v in versions.values() for m, p in pairs}, 'MISSING_PROJECT_FORECAST')
        for (version_id, _, _), values in monthly.items():
            require(sorted(values) == stored_months(versions[version_id].version_date, history, config), 'MONTHLY_HORIZON_GAP')

        selector = ForecastWindowSelector(world.forecast_versions)
        lines = {r.po_line_id: r for r in procurement.po_lines}
        for truth in scenario.scenario_truth_rows:
            line = lines[truth.po_line_id]
            anchor = forecast_anchor(line.order_date, line.material_lt_days_at_order)
            window = selector.select(dataset_id, anchor, config.after_versions_max)
            initial = monthly[(window.baseline.forecast_version_id, line.material_id, truth.causal_project_id)]
            compare_months = {add_months(anchor.replace(day=1), n) for n in range(sc.comparison_months)}
            require(compare_months <= initial.keys(), 'BASELINE_COMPARISON_MONTH_MISSING')
            for post in window.post_versions:
                values = monthly[(post.forecast_version_id, line.material_id, truth.causal_project_id)]
                require(compare_months <= values.keys(), 'POST_COMPARISON_MONTH_MISSING')
                metrics = shape_metrics(initial, values, anchor.replace(day=1), sc)
                require(matches_shape(metrics, truth.demand_change_type, sc), 'FORECAST_SCENARIO_EVIDENCE_MISMATCH')
                if truth.demand_change_type != 'NONE':
                    for material_id, project_id in pairs:
                        if material_id == line.material_id and project_id != truth.causal_project_id:
                            other = shape_metrics(monthly[(window.baseline.forecast_version_id, material_id, project_id)], monthly[(post.forecast_version_id, material_id, project_id)], anchor.replace(day=1), sc)
                            require(metrics['strength'] > other['strength'], 'CAUSAL_EVIDENCE_NOT_STRONGEST')

        weekly_projects, material_sums = defaultdict(list), defaultdict(Decimal)
        first_week = week_one_start(snapshot)
        snapshots = {sid: source.observe(sid, snapshot) for sid in signals}
        for row in world.weekly_project_forecasts:
            signal = signals[row.demand_signal_id]
            require((row.material_id, row.project_id) == (signal.material_id, signal.project_id), 'INVALID_WEEKLY_DEMAND_LINEAGE')
            require(row.organization_id == materials[row.material_id].primary_inventory_organization_id, 'INVALID_PRIMARY_ORGANIZATION')
            require(1 <= row.week_index <= 13 and row.week_start_date == first_week + timedelta(days=7 * (row.week_index - 1)), 'INVALID_WEEK_CALENDAR')
            expected = sum(snapshots[row.demand_signal_id][day] for day in days(row.week_start_date, row.week_start_date + timedelta(days=6)))
            require(row.forecast_qty == expected and row.forecast_qty >= 0, 'WEEKLY_SOURCE_RECONCILIATION')
            weekly_projects[(row.material_id, row.project_id)].append(row)
            material_sums[(row.material_id, row.week_index)] += row.forecast_qty
        require(set(weekly_projects) == set(pairs), 'WEEKLY_PROJECT_MISSING')
        for rows in weekly_projects.values():
            thirteen_week_totals(rows)
        weekly_materials = defaultdict(list)
        for row in world.weekly_forecasts:
            require(row.organization_id == materials[row.material_id].primary_inventory_organization_id, 'INVALID_PRIMARY_ORGANIZATION')
            require(row.week_start_date == first_week + timedelta(days=7 * (row.week_index - 1)), 'INVALID_MATERIAL_WEEK_CALENDAR')
            require(row.forecast_qty == material_sums[(row.material_id, row.week_index)], 'PROJECT_MATERIAL_RECONCILIATION')
            weekly_materials[row.material_id].append(row)
        require(set(weekly_materials) == set(materials), 'WEEKLY_MATERIAL_MISSING')
        zero = sum(thirteen_week_totals(rows)['thirteen_week_demand_qty'] == 0 for rows in weekly_materials.values())
        require(zero > 0 or not sc.require_all_patterns, 'ZERO_DEMAND_FIXTURE_MISSING')
        # Only compare full natural months covered by the 91-day weekly window.
        for (material_id, project_id), signal in pairs.items():
            month = first_week.replace(day=1)
            until = first_week + timedelta(days=91)
            while add_months(month, 1) <= until:
                if month >= first_week:
                    qty = sum(snapshots[signal.demand_signal_id][d] for d in days(month, add_months(month, 1) - timedelta(days=1)))
                    require(abs(qty - monthly[(latest.forecast_version_id, material_id, project_id)][month]) <= sc.forecast_rounding_tolerance, 'MONTHLY_WEEKLY_RECONCILIATION')
                month = add_months(month, 1)
        shipment_keys = set()
        quantum = Decimal(10) ** -config.rounding_scale
        for row in world.material_project_shipments:
            signal = signals[row.demand_signal_id]
            require((row.material_id, row.project_id) == (signal.material_id, signal.project_id), 'INVALID_SHIPMENT_LINEAGE')
            require(history <= row.shipment_date <= snapshot, 'SHIPMENT_OUTSIDE_HISTORY')
            observation = source.observe(row.demand_signal_id, row.shipment_date)
            planned = sum(observation[d] for d in days(max(history, row.shipment_date - timedelta(days=6)), row.shipment_date))
            require(row.shipped_qty == (planned * config.shipment_realization_ratio).quantize(quantum, rounding=ROUND_HALF_UP), 'SHIPMENT_SOURCE_MISMATCH')
            shipment_keys.add((row.material_id, row.project_id, row.shipment_date))
        require(len(shipment_keys) == len(world.material_project_shipments) and shipment_keys == {(m, p, d) for m, p in pairs for d in dates}, 'SHIPMENT_COVERAGE_MISMATCH')
