from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.generators.evidence_foundation.calendar import add_months, days
from app.generators.evidence_foundation.planning_states import persistent_daily_states
from app.generators.evidence_foundation.validation import matches_shape, publication_dry_run, shape_metrics
from app.generators.scenarios.config import ScenarioGenerationConfig
from tests.test_evidence_foundation import evidence_demo


def daily_final_window(versions, anchor, count=5):
    final = {}
    for version in versions:
        if version.is_valid and (version.version_date not in final or version.sequence_no > final[version.version_date].sequence_no):
            final[version.version_date] = version
    before = max(day for day in final if day < anchor)
    after = sorted(day for day in final if day > anchor)[:count]
    assert len(after) == count
    return final[before], [final[day] for day in after]


@pytest.mark.parametrize('anchor', [
    date(2025, 7, 21), date(2025, 7, 22), date(2025, 7, 25), date(2025, 7, 27),
    date(2025, 7, 31), date(2025, 12, 31), date(2026, 1, 1),
])
@pytest.mark.parametrize('change', ['REDUCTION', 'DELAY', 'MIXED', 'NONE'])
def test_persistent_revision_across_publication_weekdays_and_invalid_versions(anchor, change):
    sc = ScenarioGenerationConfig()
    original = {d: Decimal('80') for d in days(add_months(anchor, -2).replace(day=1), add_months(anchor, 9))}
    initial, revised = persistent_daily_states([anchor], change, sc, original, Decimal(80))
    for weekday in range(7):
        dates = [d for d in days(anchor - timedelta(days=28), anchor + timedelta(days=56)) if d.weekday() == weekday]
        for invalid in ('NONE', 'BASELINE', 'FIRST_POST'):
            skipped = (max(d for d in dates if d < anchor) if invalid == 'BASELINE' else
                       min(d for d in dates if d > anchor) if invalid == 'FIRST_POST' else None)
            versions = [SimpleNamespace(version_date=d, sequence_no=s, is_valid=d != skipped and s != 3)
                        for d in dates for s in (1, 2, 3)]
            # An anchor-day release is excluded regardless of sequence.
            versions.append(SimpleNamespace(version_date=anchor, sequence_no=9, is_valid=True))
            baseline, posts = daily_final_window(versions, anchor)
            assert baseline.version_date < anchor and baseline.sequence_no == 2
            for post in posts:
                assert post.version_date > anchor and post.sequence_no == 2
                assert matches_shape(shape_metrics(initial, revised, anchor.replace(day=1), sc), change, sc)


def test_demo_all_scenarios_all_weekly_offsets(evidence_demo):
    world, scenario, _, procurement, _, _, _, sc, _ = evidence_demo
    counts = publication_dry_run(world, scenario, procurement, sc)
    assert set(counts) == {'REDUCTION', 'DELAY', 'MIXED', 'NONE'}
    assert sum(counts.values()) == len(scenario.scenario_truth_rows) * 7 * 3 * 5
    assert {row.stockpile_flag for row in scenario.scenario_truth_rows if row.scenario_pattern == 'AFTER_SALES'} == {False, True}
    assert sc.reduction_total_drop_ratio == Decimal('0.35')


def test_mixed_rejects_pure_reduction_and_pure_delay():
    anchor = date(2025, 12, 31)
    sc = ScenarioGenerationConfig()
    original = {d: Decimal(80) for d in days(date(2025, 10, 1), date(2026, 9, 30))}
    for change in ('REDUCTION', 'DELAY'):
        initial, revised = persistent_daily_states([anchor], change, sc, original, Decimal(80))
        assert not matches_shape(shape_metrics(initial, revised, anchor.replace(day=1), sc), 'MIXED', sc)


def test_different_evidence_seed_preserves_all_demo_scenario_shapes(evidence_demo):
    from app.generators.evidence_foundation.generator import EvidenceFoundationGenerator
    from app.generators.evidence_foundation.validation import EvidenceFoundationValidator
    world, scenario, master, procurement, did, signature, config, sc, snapshot = evidence_demo
    changed_config = config.model_copy(update={'evidence_seed': config.evidence_seed + 1})
    changed = EvidenceFoundationGenerator().generate(did, snapshot, signature, changed_config, sc, master, procurement, scenario)
    EvidenceFoundationValidator().validate(changed, master, procurement, scenario, did, snapshot, changed_config, sc)
    assert changed.content_hash(signature) != world.content_hash(signature)
    assert publication_dry_run(changed, scenario, procurement, sc) == publication_dry_run(world, scenario, procurement, sc)


def test_legacy_pulse_override_is_not_silently_ignored():
    from app.generators.evidence_foundation.config import EvidenceFoundationConfig
    with pytest.raises(ValueError, match='legacy pulse settings'):
        EvidenceFoundationConfig(planning_cycle_retention=Decimal('0.8'))
