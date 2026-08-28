from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domain.operational import StockpileAsOfSelector, cumulative_age_buckets, future_months, stockpile_achievement_ratio
from app.generators.operational_evidence.config import AGE_THRESHOLDS, OperationalEvidenceConfig
from app.generators.operational_evidence.generator import OperationalEvidenceGenerator, quantity
from app.generators.operational_evidence.validation import OperationalEvidenceValidator, OperationalEvidenceValidationError
from app.generators.signature import content_hash
from app.models.platform.operational import OPERATIONAL_MODELS
from tests.test_forecasts import forecast_demo
from tests.test_evidence_foundation import evidence_demo


@pytest.fixture(scope='module')
def operational_demo(forecast_demo):
    forecast, _, _, _, foundation = forecast_demo
    evidence, scenario, master, procurement, did, _, _, sc, snapshot = foundation
    config = OperationalEvidenceConfig()
    signature = content_hash({'fixture': 'operational', 'config': config})
    args = (did, snapshot, signature, config, master, procurement, scenario, evidence, forecast)
    world = OperationalEvidenceGenerator().generate(*args)
    validation_args = (master, procurement, scenario, evidence, forecast, did, snapshot, signature, config, sc)
    validation = OperationalEvidenceValidator().validate(world, *validation_args)
    return world, args, validation_args, validation


def test_operational_inventory_supply_demand_and_all_stockpile_evidence(operational_demo):
    world, _, args, result = operational_demo
    assert len(world.inventory_snapshots) == len(args[0].materials)
    assert result['historical_lookup_hit_count'] > 0 and result['historical_lookup_miss_count'] > 0
    assert any(r.trial_all_supply_qty > 0 for r in world.supply_demand_snapshots)
    assert any(r.closing_projected_qty < 0 for r in world.stockpile_balance_projections)
    assert any(not v.is_valid for v in world.stockpile_versions)
    assert any(v.sequence_no > 1 and v.is_valid for v in world.stockpile_versions)


def test_stockpile_all_projects_as_of_revisions_not_initial_first_project(operational_demo):
    world, _, args, _ = operational_demo
    evidence = args[3]
    assert any(len(row.demand_lineage) > 1 for row in world.stockpile_forecasts)
    initial = defaultdict(Decimal)
    for point in evidence.demand_signal_points:
        initial[(str(point.demand_signal_id), point.demand_date.replace(day=1))] += point.demand_qty
    assert any(Decimal(part['forecast_qty']) != initial[(part['demand_signal_id'], row.forecast_month)]
               for row in world.stockpile_forecasts for part in row.demand_lineage)


def test_actual_demand_is_transformed_not_thirteen_week_copy(operational_demo):
    world, _, args, _ = operational_demo
    weekly = defaultdict(Decimal)
    for row in args[4].weekly_forecasts:
        weekly[row.material_id] += row.forecast_qty
    assert any(r.actual_demand_total_qty > 0 and r.actual_demand_total_qty != weekly[r.material_id]
               for r in world.supply_demand_snapshots)
    assert {r.component_type for r in world.supply_demand_components if r.component_side == 'DEMAND'} == {'WORK_ORDER_DEMAND', 'PLAN_DEMAND', 'FORECAST_DEMAND'}


def test_all_po_stockpile_plan_after_sales_both_and_current_history_difference(operational_demo):
    world, _, args, _ = operational_demo
    _, procurement, scenario, _, _, did, snapshot, *_ = args
    lines = {r.po_line_id: r for r in procurement.po_lines}
    selector = StockpileAsOfSelector(world.stockpile_versions)
    after_sales = set()
    counts = defaultdict(int)
    for truth in scenario.scenario_truth_rows:
        line = lines[truth.po_line_id]
        result = selector.lookup(world.stockpile_records, did, line.material_id, line.order_date)
        assert (result.record is not None) == truth.stockpile_flag
        assert result.version.version_date <= line.order_date
        current = selector.lookup(world.stockpile_records, did, line.material_id, snapshot)
        assert (current.record is not None) != truth.stockpile_flag
        if truth.scenario_pattern == 'AFTER_SALES':
            after_sales.add(result.record is not None)
        if truth.scenario_pattern == 'INTERNAL_SIDE_PROJECT_OBSOLESCENCE':
            assert result.status == 'MATERIAL_NOT_FOUND'
        counts[line.material_id] += 1
    assert after_sales == {False, True}
    assert max(counts.values()) > 1


@pytest.mark.parametrize('collection,field', [
    ('inventory_snapshots', 'available_qty'), ('inventory_age_buckets', 'age_qty'),
    ('supply_demand_snapshots', 'all_supply_qty'), ('supply_demand_snapshots', 'trial_all_supply_qty'),
    ('supply_demand_components', 'component_qty'), ('stockpile_records', 'target_stockpile_qty'),
    ('stockpile_forecasts', 'forecast_qty'), ('stockpile_balance_projections', 'opening_available_qty'),
    ('stockpile_inventory_age_buckets', 'age_qty'),
])
def test_operational_validator_rejects_corrupt_quantities(operational_demo, collection, field):
    world, _, args, _ = operational_demo
    row = getattr(world, collection)[0]
    value = getattr(row, field)
    try:
        setattr(row, field, value + Decimal('100000000'))
        with pytest.raises(OperationalEvidenceValidationError):
            OperationalEvidenceValidator().validate(world, *args)
    finally:
        setattr(row, field, value)


def test_stockpile_wrong_project_lineage_rejected(operational_demo):
    world, _, args, _ = operational_demo
    row = next(r for r in world.stockpile_forecasts if len(r.demand_lineage) > 1)
    previous = row.demand_lineage
    try:
        row.demand_lineage = previous[:1]
        with pytest.raises(OperationalEvidenceValidationError, match='LINEAGE'):
            OperationalEvidenceValidator().validate(world, *args)
    finally:
        row.demand_lineage = previous


def test_operational_same_seed_order_independent_and_different_seed(operational_demo):
    world, args, validation_args, _ = operational_demo
    master, procurement, evidence = args[4], args[5], args[7]
    master.materials.reverse()
    procurement.po_line_schedules.reverse()
    evidence.demand_signals.reverse()
    try:
        same = OperationalEvidenceGenerator().generate(*args)
    finally:
        master.materials.reverse()
        procurement.po_line_schedules.reverse()
        evidence.demand_signals.reverse()
    assert same.content_hash(args[2]) == world.content_hash(args[2])
    del same
    config = args[3].model_copy(update={'seed': args[3].seed + 1})
    signature = content_hash({'fixture': 'operational', 'config': config})
    other = OperationalEvidenceGenerator().generate(*args[:2], signature, config, *args[4:])
    OperationalEvidenceValidator().validate(other, *validation_args[:7], signature, config, validation_args[-1])
    assert other.content_hash(signature) != world.content_hash(args[2])
    assert [(r.material_id, r.all_supply_qty) for r in other.supply_demand_snapshots] != [(r.material_id, r.all_supply_qty) for r in world.supply_demand_snapshots]


def version(day, sequence=1, valid=True, dataset=UUID(int=1)):
    return SimpleNamespace(dataset_version_id=dataset, stockpile_version_id=f'{dataset}:{day}:{sequence}', version_date=date.fromisoformat(day), sequence_no=sequence, is_valid=valid)


def test_stockpile_selector_inclusive_same_day_invalid_and_dataset_isolation():
    did = UUID(int=1)
    rows = [version('2025-12-28'), version('2025-12-31'), version('2025-12-31', 2), version('2025-12-31', 3, False),
            version('2026-01-01', valid=False), version('2026-01-02', dataset=UUID(int=2)), version('2026-01-03')]
    selector = StockpileAsOfSelector(rows)
    assert selector.select(did, date(2025, 12, 27)) is None
    assert selector.select(did, date(2025, 12, 31)).sequence_no == 2
    assert selector.select(did, date(2026, 1, 2)).version_date == date(2025, 12, 31)
    assert selector.lookup([], did, 'material', date(2025, 12, 27)).status == 'NO_VALID_VERSION'
    assert selector.lookup([], did, 'material', date(2026, 1, 2)).status == 'MATERIAL_NOT_FOUND'


@pytest.mark.parametrize('day,first,last', [('2026-01-18', '2026-02-01', '2026-07-01'), ('2025-12-31', '2026-01-01', '2026-06-01'), ('2024-02-29', '2024-03-01', '2024-08-01')])
def test_six_natural_months(day, first, last):
    months = future_months(date.fromisoformat(day))
    assert len(months) == 6 and str(months[0]) == first and str(months[-1]) == last


def test_cumulative_inventory_age_and_zero_target_completion():
    lots = [SimpleNamespace(age_days=d, quantity=Decimal(1)) for d in (30, 31, 60, 61, 90, 91)]
    assert cumulative_age_buckets(lots, (30, 60, 90)) == {30: 5, 60: 3, 90: 1}
    assert stockpile_achievement_ratio(Decimal(1), Decimal(0)) is None
    assert stockpile_achievement_ratio(Decimal(1), Decimal(2)) == Decimal('0.5')


@pytest.mark.parametrize('values', [{'stockpile_version_frequency_days': 0}, {'availability_max': 2}, {'in_transit_ratio': -1}, {'stockpile_period_max': 7}, {'inventory_base_min': 99999}, {'unexpected_field': 1}])
def test_invalid_operational_config_rejected(values):
    with pytest.raises(ValidationError):+        OperationalEvidenceConfig(**values)


def test_operational_public_domain_and_schema_no_truth():
    import subprocess
    import sys
    subprocess.run([sys.executable, '-c', "import sys; import app.domain.operational; assert not any(n.startswith(('app.generators','app.models.evaluation')) for n in sys.modules)"], check=True, capture_output=True)
    forbidden = {'stockpile_flag', 'scenario_pattern', 'causal_project_id', 'true_cause', 'expected_action'}
    for model in OPERATIONAL_MODELS:
        assert not forbidden.intersection(model.__table__.columns.keys())
