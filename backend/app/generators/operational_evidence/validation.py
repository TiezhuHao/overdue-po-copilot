"""Independent semantic checks for operational facts and upstream lineage."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import UniqueConstraint

from app.domain.forecasts import daily_final_versions
from app.domain.operational import StockpileAsOfSelector, future_months, material_mpm_as_of
from app.models.platform.operational import OPERATIONAL_MODELS
from .config import AGE_THRESHOLDS
from .generator import DemandSource, eligible_schedules, quantity, stockpile_plan, stockpile_present, version_calendar


class OperationalEvidenceValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise OperationalEvidenceValidationError(message)


class OperationalEvidenceValidator:
    def validate(self, world, master, procurement, scenario, evidence, forecast,
                 dataset_id, snapshot, signature, config, scenario_config):
        tables = defaultdict(list)
        for row in master.all_records() + procurement.all_records():
            tables[row.__table__.fullname].append(row)
        for name in evidence.COLLECTION_NAMES:
            for row in getattr(evidence, name):
                tables[row.__table__.fullname].append(row)
        for name in forecast.counts():
            for row in getattr(forecast, name):
                tables[row.__table__.fullname].append(row)
        tables['platform.dataset_versions'] = [SimpleNamespace(dataset_version_id=dataset_id)]
        for model in OPERATIONAL_MODELS:
            tables[model.__table__.fullname] = getattr(world, model.__tablename__)
        forbidden = {'true_cause', 'scenario_pattern', 'causal_project_id', 'responsibility_type', 'expected_action', 'stockpile_flag'}
        reference_cache = {}
        for model in OPERATIONAL_MODELS:
            require(not forbidden.intersection(model.__table__.columns.keys()), 'OPERATIONAL_TRUTH_LEAKAGE')
            rows = getattr(world, model.__tablename__)
            constraints = [model.__table__.primary_key] + [c for c in model.__table__.constraints if isinstance(c, UniqueConstraint)]
            for constraint in constraints:
                keys = [tuple(getattr(r, c.key) for c in constraint.columns) for r in rows]
                require(len(keys) == len(set(keys)), 'DUPLICATE_OPERATIONAL_FACT')
            for row in rows:
                require(row.dataset_version_id == dataset_id, 'CROSS_DATASET_OPERATIONAL')
                for column in model.__table__.columns:
                    value = getattr(row, column.key)
                    if column.key.endswith('_qty') and column.key not in {
                        'supply_demand_surplus_qty', 'trial_supply_demand_surplus_qty', 'opening_available_qty', 'closing_projected_qty'}:
                        require(value is not None and value >= 0, 'NEGATIVE_OPERATIONAL_QUANTITY')
                for fk in model.__table__.foreign_key_constraints:
                    local = tuple(getattr(row, e.parent.key) for e in fk.elements)
                    if any(v is None for v in local):
                        continue
                    key = (fk.elements[0].column.table.fullname, tuple(e.column.key for e in fk.elements))
                    if key not in reference_cache:
                        reference_cache[key] = {tuple(getattr(r, field) for field in key[1]) for r in tables[key[0]]}
                    require(local in reference_cache[key], 'INVALID_OPERATIONAL_FK')

        materials = {m.material_id: m for m in master.materials}
        organizations = {o.organization_id: o for o in master.organizations}
        inventories = {r.material_id: r for r in world.inventory_snapshots}
        snapshots = {r.material_id: r for r in world.supply_demand_snapshots}
        require(set(inventories) == set(snapshots) == set(materials), 'MISSING_OPERATIONAL_MATERIAL')
        require(len(inventories) == len(world.inventory_snapshots) and len(snapshots) == len(world.supply_demand_snapshots), 'DUPLICATE_MATERIAL_GRAIN')
        source = DemandSource(evidence)
        signals = {s.demand_signal_id: s for s in evidence.demand_signals}
        latest = daily_final_versions(forecast.forecast_versions, dataset_id)[-1].forecast_version_id
        eligible = {s.po_line_schedule_id: (s, l, h) for s, l, h in eligible_schedules(procurement, snapshot)}
        components = defaultdict(list)
        windows = {}
        start = snapshot
        for kind, length, ratio in (('WORK_ORDER_DEMAND', config.work_order_days, config.work_order_ratio),
                                    ('PLAN_DEMAND', config.plan_days, config.plan_ratio),
                                    ('FORECAST_DEMAND', config.forecast_days, config.forecast_ratio)):
            end = start + timedelta(days=length - 1)
            windows[kind] = (start, end, ratio)
            start = end + timedelta(days=1)
        for row in world.supply_demand_components:
            mid = row.material_id
            require(row.supply_demand_snapshot_id == snapshots[mid].supply_demand_snapshot_id, 'INVALID_COMPONENT_SNAPSHOT')
            require(row.source_domain == 'SYNTHETIC_OPERATIONAL', 'INVALID_COMPONENT_SOURCE')
            require(row.organization_type_scope == organizations[row.organization_id].inventory_organization_type, 'INVALID_TRIAL_SCOPE')
            components[mid].append(row)
            if row.component_type == 'ON_HAND_AVAILABLE':
                require(row.component_side == 'SUPPLY' and row.inventory_snapshot_id == inventories[mid].inventory_snapshot_id
                        and row.component_qty == inventories[mid].available_qty, 'INVENTORY_SUPPLY_RECONCILIATION')
                require(row.component_key == 'inventory' and row.organization_id == materials[mid].primary_inventory_organization_id, 'INVENTORY_COMPONENT_LINEAGE')
            elif row.component_type in ('OPEN_PO', 'IN_TRANSIT'):
                require(row.po_line_schedule_id in eligible, 'INELIGIBLE_OPEN_PO')
                schedule, line, header = eligible[row.po_line_schedule_id]
                open_qty = max(schedule.schedule_qty - schedule.schedule_received_qty, Decimal(0))
                transit = quantity(open_qty * config.in_transit_ratio)
                expected = transit if row.component_type == 'IN_TRANSIT' else open_qty - transit
                require(row.component_side == 'SUPPLY' and row.component_qty == expected
                        and line.material_id == mid and row.organization_id == header.inventory_organization_id, 'OPEN_PO_RECONCILIATION')
                require(row.component_key == f'{row.component_type}:{row.po_line_schedule_id}', 'OPEN_PO_KEY')
            else:
                require(row.component_side == 'DEMAND' and row.component_type in windows, 'UNMODELED_COMPONENT')
                signal = signals.get(row.demand_signal_id)
                require(signal is not None and (signal.material_id, signal.project_id) == (mid, row.project_id), 'DEMAND_LINEAGE')
                start, end, ratio = windows[row.component_type]
                require((row.period_start, row.period_end) == (start, end) and row.source_forecast_version_id == latest, 'DEMAND_TRANSFORM_WINDOW')
                expected = quantity(source.sum(signal.demand_signal_id, snapshot, start, end) * ratio)
                require(row.component_qty == expected, 'ACTUAL_DEMAND_RECONCILIATION')
                require(row.organization_id == materials[mid].primary_inventory_organization_id and row.component_key == f'{row.component_type}:{row.demand_signal_id}', 'DEMAND_COMPONENT_KEY')
        for mid, inv in inventories.items():
            require(inv.snapshot_date == snapshot and snapshots[mid].snapshot_date == snapshot, 'WRONG_SNAPSHOT_DATE')
            require(inv.organization_id == snapshots[mid].organization_id == materials[mid].primary_inventory_organization_id, 'INVALID_PRIMARY_ORGANIZATION')
            require(inv.on_hand_qty == inv.available_qty + inv.quality_hold_qty + inv.blocked_qty, 'INVENTORY_PARTITION')
            mpm = material_mpm_as_of(master.material_mpm_assignments, dataset_id, mid, snapshot)
            require(inv.material_mpm_assignment_id == mpm.material_mpm_assignment_id, 'INVALID_MATERIAL_MPM')
            expected_keys = {'inventory'}
            expected_keys.update(f'{kind}:{sid}' for sid, (_, l, _) in eligible.items() if l.material_id == mid for kind in ('OPEN_PO', 'IN_TRANSIT'))
            expected_keys.update(f'{kind}:{s.demand_signal_id}' for s in source.signals[mid] for kind in windows)
            require({r.component_key for r in components[mid]} == expected_keys, 'INCOMPLETE_COMPONENT_COVERAGE')
            for prefix, rows in (('', components[mid]), ('trial_', [r for r in components[mid] if r.organization_type_scope == 'TRIAL'])):
                supply = sum((r.component_qty for r in rows if r.component_side == 'SUPPLY'), Decimal(0))
                demand = sum((r.component_qty for r in rows if r.component_side == 'DEMAND'), Decimal(0))
                require(getattr(snapshots[mid], prefix + 'all_supply_qty') == supply and
                        getattr(snapshots[mid], prefix + 'actual_demand_total_qty') == demand and
                        getattr(snapshots[mid], prefix + 'supply_demand_surplus_qty') == supply - demand, 'SUPPLY_DEMAND_RECONCILIATION')

        history = min(r.demand_date for r in evidence.demand_signal_points)
        expected_versions = version_calendar(dataset_id, signature, history, snapshot, procurement, config)
        fields = ('stockpile_version_id', 'version_date', 'sequence_no', 'is_valid', 'version_name', 'source_name')
        require({tuple(getattr(v, f) for f in fields) for v in world.stockpile_versions}
                == {tuple(getattr(v, f) for f in fields) for v in expected_versions}, 'INVALID_STOCKPILE_CALENDAR')
        versions = {v.stockpile_version_id: v for v in world.stockpile_versions}
        plans = stockpile_plan(scenario, procurement)
        records = {(r.stockpile_version_id, r.material_id): r for r in world.stockpile_records}
        expected_pairs = {(v.stockpile_version_id, mid) for v in versions.values() for mid in materials
                          if stockpile_present(mid, v.version_date, snapshot, plans, config)}
        require(set(records) == expected_pairs, 'INCOMPLETE_STOCKPILE_RECORDS')
        forecasts = defaultdict(dict)
        for row in world.stockpile_forecasts:
            pair = (row.stockpile_version_id, row.material_id)
            version = versions[row.stockpile_version_id]
            require(row.forecast_month in future_months(version.version_date) and row.source_observed_on == version.version_date, 'STOCKPILE_NATURAL_MONTH')
            expected_qty, lineage = source.month(row.material_id, version.version_date, row.forecast_month)
            require(row.forecast_qty == expected_qty and row.demand_lineage == lineage, 'STOCKPILE_DEMAND_LINEAGE')
            forecasts[pair][row.forecast_month] = row
        balances = defaultdict(dict)
        for row in world.stockpile_balance_projections:
            balances[(row.stockpile_version_id, row.material_id)][row.forecast_month] = row
        require(set(forecasts) == set(balances) == set(records), 'MISSING_STOCKPILE_CHILDREN')
        for pair, record in records.items():
            day = versions[pair[0]].version_date
            months = future_months(day)
            require(sorted(forecasts[pair]) == sorted(balances[pair]) == months, 'INCOMPLETE_SIX_MONTH_HORIZON')
            require(config.stockpile_period_min <= record.stockpile_period_months <= config.stockpile_period_max, 'INVALID_STOCKPILE_PERIOD')
            target = sum((forecasts[pair][m].forecast_qty for m in months[:record.stockpile_period_months]), Decimal(0))
            require(target == record.target_stockpile_qty and record.inventory_qty == record.actual_stockpile_qty, 'STOCKPILE_TARGET_RECONCILIATION')
            require(quantity(target * config.stockpile_achievement_min) <= record.actual_stockpile_qty <= quantity(target * config.stockpile_achievement_max), 'STOCKPILE_ACHIEVEMENT')
            require(record.organization_id == materials[pair[1]].primary_inventory_organization_id and record.stockpile_tag == 'PLANNED', 'STOCKPILE_ORGANIZATION')
            seven = source.material(pair[1], day, day, day + timedelta(days=6))
            remainder = source.material(pair[1], day, day, months[0] - timedelta(days=1))
            require(record.seven_day_demand_qty == seven and record.remaining_current_month_demand_qty == remainder, 'STOCKPILE_CURRENT_DEMAND')
            opening = record.inventory_qty - remainder
            inbound = quantity(target * config.stockpile_inbound_ratio / Decimal(6))
            for month in months:
                balance = balances[pair][month]
                demand = forecasts[pair][month].forecast_qty
                require(balance.opening_available_qty == opening and balance.planned_inbound_qty == inbound
                        and balance.demand_qty == demand and balance.closing_projected_qty == opening + inbound - demand, 'STOCKPILE_BALANCE_RECURRENCE')
                opening = balance.closing_projected_qty

        def check_ages(rows, parents, key):
            grouped = defaultdict(dict)
            for row in rows:
                grouped[key(row)][row.age_threshold_days] = row.age_qty
            require(set(grouped) == set(parents), 'MISSING_AGE_PARENT')
            for parent, values in grouped.items():
                require(tuple(sorted(values)) == AGE_THRESHOLDS, 'MISSING_AGE_THRESHOLDS')
                ceiling = parents[parent]
                for threshold in AGE_THRESHOLDS:
                    require(0 <= values[threshold] <= ceiling, 'AGE_NOT_CUMULATIVE')
                    ceiling = values[threshold]
        check_ages(world.inventory_age_buckets, {r.inventory_snapshot_id: r.on_hand_qty for r in inventories.values()}, lambda r: r.inventory_snapshot_id)
        check_ages(world.stockpile_inventory_age_buckets, {k: r.inventory_qty for k, r in records.items()}, lambda r: (r.stockpile_version_id, r.material_id))
        selector = StockpileAsOfSelector(world.stockpile_versions)
        lines = {r.po_line_id: r for r in procurement.po_lines}
        hit_count = 0
        after_sales = set()
        causes_by_sign = defaultdict(set)
        for truth in scenario.scenario_truth_rows:
            line = lines[truth.po_line_id]
            result = selector.lookup(world.stockpile_records, dataset_id, line.material_id, line.order_date)
            require(result.version is not None, 'MISSING_HISTORICAL_VERSION')
            found = result.record is not None
            require(found == truth.stockpile_flag, 'HISTORICAL_STOCKPILE_PLAN_MISMATCH')
            hit_count += found
            if truth.scenario_pattern == 'AFTER_SALES':
                after_sales.add(found)
            surplus = snapshots[line.material_id].supply_demand_surplus_qty
            causes_by_sign[(surplus > 0) - (surplus < 0)].add(truth.true_cause)
        if scenario_config.require_after_sales_stockpile_both:
            require(after_sales == {False, True}, 'AFTER_SALES_STOCKPILE_BOTH_MISSING')
        if scenario_config.require_all_patterns:
            require(any(len(causes) > 1 for causes in causes_by_sign.values()), 'SURPLUS_ENCODES_CAUSE')
        return {'historical_lookup_hit_count': hit_count,
                'historical_lookup_miss_count': len(scenario.scenario_truth_rows) - hit_count}
