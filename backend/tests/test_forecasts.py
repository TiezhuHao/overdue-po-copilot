from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.domain.forecasts import ForecastWindowSelector, cumulative_shipped_qty, daily_final_versions, forecast_anchor, thirteen_week_totals, top_project, week_one_start
from app.generators.config import GenerationConfig
from app.generators.forecasts.config import ForecastGenerationConfig
from app.generators.forecasts.generator import ForecastGenerator, version_calendar
from app.generators.forecasts.validation import ForecastValidationError, ForecastValidator
from app.generators.forecasts.world import forecast_signature
from app.generators.signature import generation_signature
from app.models.platform.forecasts import FORECAST_MODELS
from tests.test_evidence_foundation import evidence_demo

DID = UUID(int=1)


def version(day, sequence=1, valid=True, dataset=DID):
    return SimpleNamespace(dataset_version_id=dataset, version_date=date.fromisoformat(day), sequence_no=sequence, is_valid=valid)


def test_anchor_and_strict_baseline_post_selection():
    anchor = forecast_anchor(date(2024, 5, 12), 30)
    assert anchor == date(2024, 6, 11)
    versions = [version('2024-06-03'), version('2024-06-10'), version('2024-06-11'), version('2024-06-12'), version('2024-06-19')]
    window = ForecastWindowSelector(versions).select(DID, anchor, 2)
    assert window.baseline.version_date == date(2024, 6, 10)
    assert [v.version_date for v in window.post_versions] == [date(2024, 6, 12), date(2024, 6, 19)]
    assert window.ordered_window == (window.baseline, *window.post_versions)


def test_invalid_sequences_and_dataset_isolation():
    rows = [version('2024-06-03'), version('2024-06-10', valid=False),
            version('2024-06-12'), version('2024-06-12', 2), version('2024-06-12', 3, False),
            version('2024-06-19'), version('2024-06-20', dataset=UUID(int=2))]
    window = ForecastWindowSelector(rows).select(DID, date(2024, 6, 11), 2)
    assert window.baseline.version_date == date(2024, 6, 3)
    assert window.post_versions[0].sequence_no == 2
    assert len(daily_final_versions(rows, DID)) == 3


@pytest.mark.parametrize('count', [2, 3, 4, 5])
def test_window_sizes_cross_year(count):
    rows = [version('2025-12-29')] + [version(f'2026-01-{day:02d}') for day in (1, 8, 15, 22, 29)]
    assert len(ForecastWindowSelector(rows).select(DID, date(2025, 12, 31), count).ordered_window) == count + 1


@pytest.mark.parametrize('count', [0, 1, 6, True, 2.5])
def test_invalid_window_sizes(count):
    with pytest.raises(ValueError, match='AFTER_VERSIONS'):
        ForecastWindowSelector([]).select(DID, date(2025, 1, 1), count)


def test_missing_window_rejected():
    with pytest.raises(ValueError, match='INCOMPLETE_FORECAST_WINDOW'):
        ForecastWindowSelector([]).select(DID, date(2025, 1, 1))
    with pytest.raises(ValueError, match='INCOMPLETE_FORECAST_WINDOW'):
        ForecastWindowSelector([version('2024-12-30'), version('2025-01-06')]).select(DID, date(2025, 1, 1), 2)


@pytest.mark.parametrize('snapshot,expected', [(date(2026, 8, 24), date(2026, 8, 24)), (date(2026, 8, 26), date(2026, 8, 31)), (date(2025, 12, 31), date(2026, 1, 5))])
def test_monday_start(snapshot, expected):
    assert week_one_start(snapshot) == expected


def test_zero_demand_and_top_project_numerical_queries():
    rows = [SimpleNamespace(week_index=i, forecast_qty=Decimal(0)) for i in range(1, 14)]
    assert thirteen_week_totals(rows) == {'thirteen_week_demand_qty': Decimal(0), 'weekly_average_demand_qty': Decimal(0)}
    projects = [SimpleNamespace(project_id=UUID(int=i), forecast_qty=Decimal(5)) for i in (2, 1)]
    assert top_project(projects) == UUID(int=1)
    projects[0].forecast_qty = Decimal(6)
    assert top_project(projects) == UUID(int=2)


def test_cumulative_shipments_inclusive_as_of_and_scoped():
    rows = [SimpleNamespace(dataset_version_id=DID, material_id=1, project_id=2, shipment_date=date(2025, 1, day), shipped_qty=Decimal(day)) for day in (1, 2, 3)]
    assert cumulative_shipped_qty(rows, DID, 1, 2, date(2025, 1, 2)) == 3
    assert cumulative_shipped_qty(rows, UUID(int=2), 1, 2, date(2025, 1, 2)) == 0


@pytest.fixture(scope='module')
def forecast_demo(evidence_demo):
    evidence, scenario, master, procurement, did, es, _, sc, snapshot = evidence_demo
    config = ForecastGenerationConfig()
    ds = generation_signature(GenerationConfig.demo())
    signature = forecast_signature(ds, evidence.content_hash(es), config)
    world = ForecastGenerator().generate(did, ds, snapshot, signature, config, master, evidence)
    ForecastValidator().validate(world, master, procurement, scenario, evidence, did, ds, snapshot, config, sc)
    return world, signature, config, ds, evidence_demo


def test_demo_forecast_lineage_calendar_and_all_scenario_evidence(forecast_demo):
    world, _, _, _, foundation = forecast_demo
    evidence = foundation[0]
    assert len(world.weekly_project_forecasts) == len(evidence.demand_signals) * 13
    assert len(world.weekly_forecasts) == len(foundation[2].materials) * 13
    assert any(not v.is_valid for v in world.forecast_versions)
    assert any(v.sequence_no > 1 and v.is_valid for v in world.forecast_versions)
    totals = defaultdict(Decimal)
    for row in world.weekly_forecasts:
        totals[row.material_id] += row.forecast_qty
    assert any(q == 0 for q in totals.values())


def test_forecast_same_and_different_seed(forecast_demo):
    world, signature, config, ds, foundation = forecast_demo
    evidence, scenario, master, procurement, did, _, _, sc, snapshot = foundation
    same = ForecastGenerator().generate(did, ds, snapshot, signature, config, master, evidence)
    assert same.content_hash(signature) == world.content_hash(signature)
    del same
    changed_config = config.model_copy(update={'seed': config.seed + 1})
    changed_signature = forecast_signature(ds, evidence.content_hash(foundation[5]), changed_config)
    changed = ForecastGenerator().generate(did, ds, snapshot, changed_signature, changed_config, master, evidence)
    ForecastValidator().validate(changed, master, procurement, scenario, evidence, did, ds, snapshot, changed_config, sc)
    assert changed.content_hash(changed_signature) != world.content_hash(signature)
    original = {(v.version_date, v.sequence_no): v.forecast_version_id for v in world.forecast_versions}
    assert all(original.get((v.version_date, v.sequence_no), v.forecast_version_id) == v.forecast_version_id for v in changed.forecast_versions)
    assert [r.forecast_qty for r in world.weekly_project_forecasts] == [r.forecast_qty for r in changed.weekly_project_forecasts]


@pytest.mark.parametrize('collection', ['monthly_forecasts', 'weekly_project_forecasts', 'weekly_forecasts'])
def test_corrupted_quantities_fail_reconciliation(forecast_demo, collection):
    world, _, config, ds, foundation = forecast_demo
    evidence, scenario, master, procurement, did, _, _, sc, snapshot = foundation
    row = getattr(world, collection)[0]
    original = row.forecast_qty
    try:
        row.forecast_qty += Decimal('1')
        with pytest.raises(ForecastValidationError, match='RECONCILIATION'):
            ForecastValidator().validate(world, master, procurement, scenario, evidence, did, ds, snapshot, config, sc)
    finally:
        row.forecast_qty = original


def test_forecast_schema_has_no_truth_or_wide_columns():
    forbidden = {'causal_project_id', 'scenario_pattern', 'true_cause', 'demand_change_type', 'expected_action', 'forecast_qty_m0', 'week_01_forecast_qty'}
    for model in FORECAST_MODELS:
        assert not forbidden.intersection(model.__table__.columns.keys())


def test_wrong_existing_signal_is_rejected(forecast_demo):
    world, _, config, ds, foundation = forecast_demo
    evidence, scenario, master, procurement, did, _, _, sc, snapshot = foundation
    row = world.monthly_forecasts[0]
    original = row.demand_signal_id
    try:
        row.demand_signal_id = next(s.demand_signal_id for s in evidence.demand_signals if s.demand_signal_id != original)
        with pytest.raises(ForecastValidationError, match='LINEAGE'):
            ForecastValidator().validate(world, master, procurement, scenario, evidence, did, ds, snapshot, config, sc)
    finally:
        row.demand_signal_id = original


def test_forecast_query_domain_does_not_load_generator_or_truth():
    import subprocess
    import sys
    code = "import sys; import app.domain.forecasts; assert not any(n.startswith(('app.generators', 'app.models.evaluation')) for n in sys.modules)"
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True)


def test_missing_demand_never_falls_back_to_random():
    with pytest.raises(ValueError, match='INCOMPLETE_EVIDENCE_FOUNDATION'):
        ForecastGenerator().generate(DID, 'dataset', date(2026, 8, 26), 'signature', ForecastGenerationConfig(), None,
                                     SimpleNamespace(demand_signals=[], demand_signal_points=[]))
