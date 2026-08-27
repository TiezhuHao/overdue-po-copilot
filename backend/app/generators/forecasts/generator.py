from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from random import Random

from app.core.ids import deterministic_uuid
from app.domain.forecasts import daily_final_versions, week_one_start
from app.generators.evidence_foundation.calendar import add_months, days
from app.generators.evidence_foundation.world import DemandObservationIndex
from app.generators.forecasts.world import ForecastWorld
from app.models.platform.forecasts import ForecastVersion, MaterialProjectShipment, MonthlyForecast, WeeklyForecast, WeeklyForecastSnapshot, WeeklyProjectForecast


def version_calendar(dataset_id, dataset_signature, history_start, snapshot, config):
    dates = list(days(week_one_start(history_start), snapshot))[::config.version_frequency_days]
    if len(dates) < 8:
        raise ValueError('INSUFFICIENT_FORECAST_HISTORY')
    rng = Random(config.seed)
    invalid = set()
    last_invalid = -7
    # At most one entirely invalid publication within any six-week window.
    forced = 3 + rng.randrange(min(4, len(dates) - 4))
    for i in range(3, len(dates) - 1):
        if i - last_invalid >= 7 and (rng.random() < config.invalid_version_fixture_rate or (i == forced and config.invalid_version_fixture_rate > 0)):
            invalid.add(i)
            last_invalid = i
    rows = []
    for i, day in enumerate(dates):
        revisions = i in (1, 2) or rng.random() < config.revision_probability
        sequences = (1, 2, 3) if revisions and i % 2 else (1, 2) if revisions else (1,)
        for sequence in sequences:
            valid = i not in invalid and (sequence == 1 or sequence == 2 and i % 2 == 1)
            rows.append(ForecastVersion(
                dataset_version_id=dataset_id,
                forecast_version_id=deterministic_uuid(dataset_signature, 'forecast_version', f'{day}:{sequence}'),
                version_name=f'PLAN-{day.isoformat()}-{sequence:02d}', version_date=day,
                sequence_no=sequence, is_valid=valid,
                description='Synthetic weekly planning publication',
            ))
    return rows


def stored_months(version_date, history_start, config):
    month = max(history_start.replace(day=1), add_months(version_date.replace(day=1), -config.comparison_lookback_months))
    end = add_months(version_date.replace(day=1), config.monthly_horizon_months + config.comparison_forward_months)
    result = []
    while month < end:
        result.append(month)
        month = add_months(month, 1)
    return result


class ForecastGenerator:
    def generate(self, dataset_id, dataset_signature, snapshot, signature, config, master, evidence):
        if not evidence.demand_signal_points or not evidence.demand_signals:
            raise ValueError('INCOMPLETE_EVIDENCE_FOUNDATION')
        world = ForecastWorld()
        history_start = min(r.demand_date for r in evidence.demand_signal_points)
        world.forecast_versions = version_calendar(dataset_id, dataset_signature, history_start, snapshot, config)
        versions_by_date = defaultdict(list)
        for version in world.forecast_versions:
            versions_by_date[version.version_date].append(version)
        latest = daily_final_versions(world.forecast_versions, dataset_id)[-1]
        snapshot_id = deterministic_uuid(signature, 'weekly_forecast_snapshot', snapshot)
        world.weekly_forecast_snapshots.append(WeeklyForecastSnapshot(
            dataset_version_id=dataset_id, weekly_forecast_snapshot_id=snapshot_id,
            snapshot_date=snapshot, source_forecast_version_id=latest.forecast_version_id, is_latest=True,
        ))
        source = DemandObservationIndex(evidence)
        materials = {r.material_id: r for r in master.materials}
        material_weeks = defaultdict(Decimal)
        first_week = week_one_start(snapshot)
        quantum = Decimal(10) ** -config.rounding_scale
        for signal in sorted(evidence.demand_signals, key=lambda r: (str(r.material_id), str(r.project_id))):
            common = dict(dataset_version_id=dataset_id, material_id=signal.material_id,
                          project_id=signal.project_id, demand_signal_id=signal.demand_signal_id)
            for day in sorted(versions_by_date):
                observation = source.observe(signal.demand_signal_id, day)
                months = defaultdict(Decimal)
                for demand_date, qty in observation.items():
                    months[demand_date.replace(day=1)] += qty
                for month in stored_months(day, history_start, config):
                    if add_months(month, 1) - timedelta(days=1) not in observation:
                        raise ValueError('INCOMPLETE_FORECAST_MONTH_HORIZON')
                    for version in versions_by_date[day]:
                        world.monthly_forecasts.append(MonthlyForecast(
                            **common, forecast_version_id=version.forecast_version_id,
                            forecast_month=month, forecast_qty=months[month], forecast_source=config.forecast_source,
                        ))
                shipped = sum((observation[d] for d in days(max(history_start, day - timedelta(days=6)), day)), Decimal(0))
                world.material_project_shipments.append(MaterialProjectShipment(
                    **common, material_project_shipment_id=deterministic_uuid(signature, 'project_shipment', f'{signal.demand_signal_id}:{day}'),
                    shipment_date=day, shipped_qty=(shipped * config.shipment_realization_ratio).quantize(quantum, rounding=ROUND_HALF_UP),
                ))
            observation = source.observe(signal.demand_signal_id, snapshot)
            for index in range(1, config.weekly_horizon_weeks + 1):
                week_start = first_week + timedelta(days=7 * (index - 1))
                try:
                    quantity = sum((observation[d] for d in days(week_start, week_start + timedelta(days=6))), Decimal(0))
                except KeyError as exc:
                    raise ValueError('INCOMPLETE_FORECAST_WEEK_HORIZON') from exc
                organization = materials[signal.material_id].primary_inventory_organization_id
                world.weekly_project_forecasts.append(WeeklyProjectForecast(
                    **common, weekly_forecast_snapshot_id=snapshot_id, organization_id=organization,
                    week_index=index, week_start_date=week_start, forecast_qty=quantity,
                ))
                material_weeks[(signal.material_id, index)] += quantity
        for (material_id, index), quantity in sorted(material_weeks.items(), key=lambda item: (str(item[0][0]), item[0][1])):
            world.weekly_forecasts.append(WeeklyForecast(
                dataset_version_id=dataset_id, weekly_forecast_snapshot_id=snapshot_id,
                material_id=material_id, organization_id=materials[material_id].primary_inventory_organization_id,
                week_index=index, week_start_date=first_week + timedelta(days=7 * (index - 1)), forecast_qty=quantity,
            ))
        return world
