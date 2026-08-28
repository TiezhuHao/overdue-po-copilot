"""Construct operational facts from upstream worlds, never from report totals."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from hashlib import sha256
from random import Random

from app.core.ids import deterministic_uuid
from app.domain.forecasts import daily_final_versions
from app.domain.operational import future_months, material_mpm_as_of
from app.generators.evidence_foundation.calendar import add_months, days
from app.generators.evidence_foundation.world import DemandObservationIndex
from app.models.platform.operational import (
    InventorySnapshot, InventoryAgeBucket, SupplyDemandSnapshot, SupplyDemandComponent,
    StockpileVersion, StockpileRecord, StockpileForecast, StockpileBalanceProjection,
    StockpileInventoryAgeBucket,
)
from .config import AGE_THRESHOLDS
from .world import OperationalEvidenceWorld


def quantity(value):
    return Decimal(value).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def rng_for(config, key):
    return Random(int(sha256(f'{config.seed}:{key}'.encode()).hexdigest(), 16))


def uniform(rng, lower, upper):
    return lower + (upper - lower) * Decimal(rng.randrange(10001)) / Decimal(10000)


def age_distribution(total, rng, config):
    remaining = total
    result = {}
    for threshold in AGE_THRESHOLDS:
        remaining = quantity(remaining * uniform(rng, config.age_retention_min, config.age_retention_max))
        result[threshold] = remaining
    return result


class DemandSource:
    """Bounded cache of full effective-dated observations, with explicit missing-day rejection."""
    def __init__(self, evidence):
        if not evidence.demand_signals or not evidence.demand_signal_points:
            raise ValueError('INCOMPLETE_EVIDENCE_FOUNDATION')
        self.signals = defaultdict(list)
        for signal in sorted(evidence.demand_signals, key=lambda s: str(s.demand_signal_id)):
            self.signals[signal.material_id].append(signal)
        self.index = DemandObservationIndex(evidence)
        self.observe = lru_cache(maxsize=256)(self.index.observe)

    def sum(self, signal_id, as_of, start, end):
        observed = self.observe(signal_id, as_of)
        try:
            return sum((observed[d] for d in days(start, end)), Decimal(0))
        except KeyError as exc:
            raise ValueError('INCOMPLETE_OPERATIONAL_DEMAND_HORIZON') from exc

    def material(self, material_id, as_of, start, end):
        if material_id not in self.signals:
            raise ValueError('MISSING_MATERIAL_DEMAND_LINEAGE')
        return sum((self.sum(s.demand_signal_id, as_of, start, end)
                    for s in self.signals[material_id]), Decimal(0))

    def month(self, material_id, as_of, month):
        lineage = []
        for signal in self.signals[material_id]:
            qty = self.sum(signal.demand_signal_id, as_of, month, add_months(month, 1) - timedelta(days=1))
            lineage.append({'demand_signal_id': str(signal.demand_signal_id),
                            'project_id': str(signal.project_id), 'forecast_qty': format(qty, '.4f')})
        return sum((Decimal(r['forecast_qty']) for r in lineage), Decimal(0)), lineage


def eligible_schedules(procurement, snapshot):
    lines = {r.po_line_id: r for r in procurement.po_lines}
    headers = {r.po_header_id: r for r in procurement.po_headers}
    result = []
    for schedule in sorted(procurement.po_line_schedules, key=lambda r: str(r.po_line_schedule_id)):
        line = lines[schedule.po_line_id]
        header = headers[line.po_header_id]
        if (line.order_date <= snapshot and schedule.close_status == 'OPEN' and header.close_status == 'OPEN'
                and line.line_status in ('OPEN', 'PARTIALLY_RECEIVED')
                and header.po_status in ('OPEN', 'PARTIALLY_RECEIVED')):
            result.append((schedule, line, header))
    return result


def stockpile_plan(scenario, procurement):
    lines = {r.po_line_id: r for r in procurement.po_lines}
    result = {}
    for truth in scenario.scenario_truth_rows:
        material_id = lines[truth.po_line_id].material_id
        if material_id in result and result[material_id] != truth.stockpile_flag:
            raise ValueError('INCONSISTENT_MATERIAL_STOCKPILE_PLAN')
        result[material_id] = truth.stockpile_flag
    return result


def stockpile_present(material_id, version_date, snapshot, plans, config):
    if material_id in plans:
        # Current/post-snapshot counterexamples never replace historical PO evidence.
        return plans[material_id] if version_date < snapshot else not plans[material_id]
    return rng_for(config, f'membership:{material_id}:{version_date.year}:{version_date.month}').randrange(3) == 0


def version_calendar(dataset_id, signature, history, snapshot, procurement, config):
    earliest_order = min(r.order_date for r in procurement.po_lines)
    if history > earliest_order:
        raise ValueError('INSUFFICIENT_STOCKPILE_HISTORY')
    dates = set(list(days(history, snapshot))[::config.stockpile_version_frequency_days])
    dates.update((earliest_order, snapshot, snapshot + timedelta(days=7)))
    result = []
    for index, day in enumerate(sorted(dates)):
        sequences = (1, 2, 3) if index == 2 or day == earliest_order else (1,)
        for sequence in sequences:
            result.append(StockpileVersion(
                dataset_version_id=dataset_id,
                stockpile_version_id=deterministic_uuid(signature, 'stockpile_version', f'{day}:{sequence}'),
                version_name=f'STOCK-{day}-{sequence:02d}', version_date=day, sequence_no=sequence,
                is_valid=(index != 1 or day == earliest_order) and sequence != 3,
                source_name='SYNTHETIC_STOCKPILE_PLAN'))
    return result


class OperationalEvidenceGenerator:
    def generate(self, dataset_id, snapshot, signature, config, master, procurement, scenario, evidence, forecast):
        world = OperationalEvidenceWorld()
        source = DemandSource(evidence)
        common = {'dataset_version_id': dataset_id}
        materials = sorted(master.materials, key=lambda r: str(r.material_id))
        organizations = {r.organization_id: r for r in master.organizations}
        latest = daily_final_versions(forecast.forecast_versions, dataset_id)
        if not latest:
            raise ValueError('INCOMPLETE_FORECAST_WORLD')
        latest_id = latest[-1].forecast_version_id
        eligible = defaultdict(list)
        for schedule, line, header in eligible_schedules(procurement, snapshot):
            eligible[line.material_id].append((schedule, header))
        windows = []
        start = snapshot
        for kind, length, ratio in (
            ('WORK_ORDER_DEMAND', config.work_order_days, config.work_order_ratio),
            ('PLAN_DEMAND', config.plan_days, config.plan_ratio),
            ('FORECAST_DEMAND', config.forecast_days, config.forecast_ratio),
        ):
            end = start + timedelta(days=length - 1)
            windows.append((kind, start, end, ratio))
            start = end + timedelta(days=1)

        for material in materials:
            mid, oid = material.material_id, material.primary_inventory_organization_id
            scope = organizations[oid].inventory_organization_type
            rand = rng_for(config, f'inventory:{mid}')
            next_demand = source.material(mid, snapshot, snapshot, windows[-1][2])
            on_hand = quantity(uniform(rand, config.inventory_base_min, config.inventory_base_max)
                               + next_demand * uniform(rand, config.inventory_demand_cover_min, config.inventory_demand_cover_max))
            available = quantity(on_hand * uniform(rand, config.availability_min, config.availability_max))
            hold = quantity((on_hand - available) * Decimal('0.4'))
            inventory_id = deterministic_uuid(signature, 'inventory', mid)
            mpm = material_mpm_as_of(master.material_mpm_assignments, dataset_id, mid, snapshot)
            world.inventory_snapshots.append(InventorySnapshot(
                **common, inventory_snapshot_id=inventory_id, snapshot_date=snapshot, material_id=mid,
                organization_id=oid, material_mpm_assignment_id=mpm.material_mpm_assignment_id,
                on_hand_qty=on_hand, available_qty=available, quality_hold_qty=hold,
                blocked_qty=on_hand - available - hold))
            for threshold, qty in age_distribution(on_hand, rand, config).items():
                world.inventory_age_buckets.append(InventoryAgeBucket(
                    **common, inventory_age_bucket_id=deterministic_uuid(signature, 'inventory_age', f'{mid}:{threshold}'),
                    inventory_snapshot_id=inventory_id, age_threshold_days=threshold, age_qty=qty))
            snapshot_id = deterministic_uuid(signature, 'supply_demand', mid)
            components = []

            def component(kind, side, qty, key, organization=oid, **lineage):
                components.append(SupplyDemandComponent(
                    **common, supply_demand_component_id=deterministic_uuid(signature, 'component', f'{mid}:{key}'),
                    supply_demand_snapshot_id=snapshot_id, material_id=mid, organization_id=organization,
                    component_key=key, component_type=kind, component_side=side,
                    organization_type_scope=organizations[organization].inventory_organization_type,
                    source_domain='SYNTHETIC_OPERATIONAL', component_qty=quantity(qty), **lineage))

            component('ON_HAND_AVAILABLE', 'SUPPLY', available, 'inventory', inventory_snapshot_id=inventory_id)
            for schedule, header in eligible[mid]:
                open_qty = max(schedule.schedule_qty - schedule.schedule_received_qty, Decimal(0))
                transit = quantity(open_qty * config.in_transit_ratio)
                for kind, qty in (('OPEN_PO', open_qty - transit), ('IN_TRANSIT', transit)):
                    component(kind, 'SUPPLY', qty, f'{kind}:{schedule.po_line_schedule_id}',
                              organization=header.inventory_organization_id,
                              po_line_schedule_id=schedule.po_line_schedule_id)
            for signal in source.signals[mid]:
                for kind, start, end, ratio in windows:
                    planned = source.sum(signal.demand_signal_id, snapshot, start, end)
                    component(kind, 'DEMAND', quantity(planned * ratio), f'{kind}:{signal.demand_signal_id}',
                              project_id=signal.project_id, demand_signal_id=signal.demand_signal_id,
                              source_forecast_version_id=latest_id, period_start=start, period_end=end)
            world.supply_demand_components.extend(components)
            totals = {}
            for prefix, rows in (('', components), ('trial_', [r for r in components if r.organization_type_scope == 'TRIAL'])):
                supply = sum((r.component_qty for r in rows if r.component_side == 'SUPPLY'), Decimal(0))
                demand = sum((r.component_qty for r in rows if r.component_side == 'DEMAND'), Decimal(0))
                totals.update({prefix + 'all_supply_qty': supply, prefix + 'actual_demand_total_qty': demand,
                               prefix + 'supply_demand_surplus_qty': supply - demand})
            world.supply_demand_snapshots.append(SupplyDemandSnapshot(
                **common, supply_demand_snapshot_id=snapshot_id, snapshot_date=snapshot,
                material_id=mid, organization_id=oid, **totals))

        history = min(p.demand_date for p in evidence.demand_signal_points)
        world.stockpile_versions = version_calendar(dataset_id, signature, history, snapshot, procurement, config)
        plans = stockpile_plan(scenario, procurement)
        for version in world.stockpile_versions:
            day, vid = version.version_date, version.stockpile_version_id
            months = future_months(day)
            for material in materials:
                mid = material.material_id
                if not stockpile_present(mid, day, snapshot, plans, config):
                    continue
                rand = rng_for(config, f'stockpile:{mid}:{day}')
                period = rand.randint(config.stockpile_period_min, config.stockpile_period_max)
                demands = [source.month(mid, day, month) for month in months]
                target = sum((qty for qty, _ in demands[:period]), Decimal(0))
                actual = quantity(target * uniform(rand, config.stockpile_achievement_min, config.stockpile_achievement_max))
                seven = source.material(mid, day, day, day + timedelta(days=6))
                remainder = source.material(mid, day, day, months[0] - timedelta(days=1))
                world.stockpile_records.append(StockpileRecord(
                    **common, stockpile_record_id=deterministic_uuid(signature, 'stockpile_record', f'{vid}:{mid}'),
                    stockpile_version_id=vid, material_id=mid,
                    organization_id=material.primary_inventory_organization_id, stockpile_tag='PLANNED',
                    stockpile_period_months=period, target_stockpile_qty=target, actual_stockpile_qty=actual,
                    inventory_qty=actual, seven_day_demand_qty=seven, remaining_current_month_demand_qty=remainder))
                opening = actual - remainder
                inbound = quantity(target * config.stockpile_inbound_ratio / Decimal(6))
                for month, (qty, lineage) in zip(months, demands, strict=True):
                    key = f'{vid}:{mid}:{month}'
                    world.stockpile_forecasts.append(StockpileForecast(
                        **common, stockpile_forecast_id=deterministic_uuid(signature, 'stockpile_forecast', key),
                        stockpile_version_id=vid, material_id=mid, forecast_month=month,
                        source_observed_on=day, demand_lineage=lineage, forecast_qty=qty))
                    closing = opening + inbound - qty
                    world.stockpile_balance_projections.append(StockpileBalanceProjection(
                        **common, stockpile_balance_projection_id=deterministic_uuid(signature, 'stockpile_balance', key),
                        stockpile_version_id=vid, material_id=mid, forecast_month=month,
                        opening_available_qty=opening, planned_inbound_qty=inbound, demand_qty=qty, closing_projected_qty=closing))
                    opening = closing
                for threshold, qty in age_distribution(actual, rand, config).items():
                    world.stockpile_inventory_age_buckets.append(StockpileInventoryAgeBucket(
                        **common, stockpile_inventory_age_bucket_id=deterministic_uuid(signature, 'stockpile_age', f'{vid}:{mid}:{threshold}'),
                        stockpile_version_id=vid, material_id=mid, age_threshold_days=threshold, age_qty=qty))
        return world
