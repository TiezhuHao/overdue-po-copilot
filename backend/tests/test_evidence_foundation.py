from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from random import Random

import pytest
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import ExcludeConstraint

from app.core.ids import deterministic_uuid
from app.generators.config import GenerationConfig
from app.generators.context import GenerationContext
from app.generators.evidence_foundation.calendar import active, add_months, demand_horizon, material_anchors, source_cycles
from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.generator import EvidenceFoundationGenerator, changed_quantities
from app.generators.evidence_foundation.validation import EvidenceFoundationValidator, future_statistics, has_after_sales_quantities, shape_metrics
from app.generators.evidence_foundation.world import DemandObservationIndex, evidence_signature
from app.generators.master_data.generator import MasterDataGenerator
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.generator import ProcurementGenerator
from app.generators.procurement.signature import procurement_generation_signature
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.planner import ScenarioPlanner
from app.generators.scenarios.signature import scenario_generation_signature
from app.generators.signature import generation_signature
from app.models.platform.evidence_foundation import EVIDENCE_MODELS, DemandSignal, DemandSignalPoint, ProductConfig, ProjectLifecycleHistory
from tests.test_scenario_planning import _scenario


@pytest.fixture(scope="module")
def evidence_demo():
    scenario, master, procurement, dataset_id, signature, sc, snapshot = _scenario()
    config = EvidenceFoundationConfig()
    world = EvidenceFoundationGenerator().generate(dataset_id, snapshot, signature, config, sc, master, procurement, scenario)
    EvidenceFoundationValidator().validate(world, master, procurement, scenario, dataset_id, snapshot, config, sc)
    return world, scenario, master, procurement, dataset_id, signature, config, sc, snapshot


def small_evidence(seed=20260829, snapshot=date(2026, 8, 26)):
    mc = GenerationConfig.small_test(snapshot_date=snapshot)
    ms = generation_signature(mc)
    dataset_id = deterministic_uuid(ms, "dataset_version", ms)
    master = MasterDataGenerator().generate(GenerationContext(dataset_id, ms, mc, Random(mc.random_seed)))
    pc = ProcurementGenerationConfig.small_test()
    ps = procurement_generation_signature(ms, pc)
    procurement = ProcurementGenerator().generate(dataset_id, snapshot, ps, pc, master)
    sc = ScenarioGenerationConfig.small_test()
    ss = scenario_generation_signature(ms, procurement.procurement_facts_hash(), sc)
    scenario = ScenarioPlanner().plan(dataset_id, snapshot, ss, sc, master, procurement)
    config = EvidenceFoundationConfig(evidence_seed=seed)
    signature = evidence_signature(ms, master.master_content_hash(ms), procurement.procurement_facts_hash(), scenario.scenario_content_hash(ss), sc, config)
    world = EvidenceFoundationGenerator().generate(dataset_id, snapshot, signature, config, sc, master, procurement, scenario)
    EvidenceFoundationValidator().validate(world, master, procurement, scenario, dataset_id, snapshot, config, sc)
    return world, signature


def test_project_lifecycle_schema():
    table = ProjectLifecycleHistory.__table__
    assert set(table.columns.keys()) == {"dataset_version_id", "project_lifecycle_id", "project_id", "lifecycle_stage", "effective_from", "effective_to", "created_at"}
    assert any(isinstance(c, ExcludeConstraint) for c in table.constraints)
    assert "AFTER_SALES" not in " ".join(str(getattr(c, "sqltext", "")) for c in table.constraints)


def test_scenario_lifecycle_requirement(evidence_demo):
    world, scenario, master, _, _, _, _, _, snapshot = evidence_demo
    current = defaultdict(list)
    for row in world.project_lifecycle_history:
        if active(row, snapshot):
            current[row.project_id].append(row.lifecycle_stage)
    assert set(current) == {row.project_id for row in master.projects}
    assert all(len(values) == 1 for values in current.values())
    assert all(current[pid] == [stage] for pid, stage in scenario.project_lifecycle_requirements.items())


def test_project_lifecycle_half_open_boundaries(evidence_demo):
    world = evidence_demo[0]
    for row in world.project_lifecycle_history:
        assert active(row, row.effective_from)
        if row.effective_to:
            assert not active(row, row.effective_to)


def test_product_config_generation_and_project_cardinality(evidence_demo):
    world, _, master, _, _, _, config, _, snapshot = evidence_demo
    counts = Counter(row.project_id for row in world.product_configs)
    assert set(counts) == {row.project_id for row in master.projects}
    assert all(count == config.configs_per_project for count in counts.values())
    assert "material_id" not in ProductConfig.__table__.columns
    assert all(active(row, snapshot) for row in world.product_configs)


def test_product_config_material_relation(evidence_demo):
    world, _, master, *_ = evidence_demo
    config_projects = {row.product_config_id: row.project_id for row in world.product_configs}
    actual = {(row.material_id, config_projects[row.product_config_id]) for row in world.product_config_materials}
    assert actual == {(row.material_id, row.project_id) for row in master.material_projects}
    assert max(Counter(row.product_config_id for row in world.product_config_materials).values()) > 1


def test_product_config_customer_organization_and_representative(evidence_demo):
    world, _, master, _, _, _, _, _, snapshot = evidence_demo
    orgs = {row.organization_id: row for row in master.organizations}
    for row in world.product_configs:
        assert any(rel.project_id == row.project_id and rel.customer_id == row.customer_id and rel.relationship_type == "PRIMARY" and active(rel, snapshot) for rel in master.project_customers)
        assert orgs[row.business_unit_id].organization_type == "BUSINESS_UNIT"
        assert orgs[row.planning_department_id].parent_organization_id == row.business_unit_id
        assert any(rel.employee_id == row.research_representative_employee_id and rel.role_type == "RESEARCH_REPRESENTATIVE" and active(rel, snapshot) for rel in master.employee_role_assignments)


def test_demand_signal_schema_and_date_uniqueness(evidence_demo):
    for model in EVIDENCE_MODELS:
        for fk in model.__table__.constraints:
            if isinstance(fk, ForeignKeyConstraint):
                assert "dataset_version_id" in fk.columns.keys()
    unique_sets = {tuple(column.key for column in c.columns) for c in DemandSignalPoint.__table__.constraints if isinstance(c, UniqueConstraint)}
    assert ("dataset_version_id", "demand_signal_id", "demand_date") in unique_sets
    rows = evidence_demo[0].demand_signal_points
    assert len(rows) == len({(row.demand_signal_id, row.demand_date) for row in rows})


def test_demand_qty_nonnegative_and_horizon(evidence_demo):
    world, scenario, _, procurement, _, _, config, _, snapshot = evidence_demo
    start, end = demand_horizon(snapshot, scenario, procurement, config)
    assert min(row.demand_date for row in world.demand_signal_points) == start
    assert max(row.demand_date for row in world.demand_signal_points) == end
    assert end >= add_months(snapshot, 8)
    earliest = min(anchor for values in material_anchors(scenario, procurement).values() for anchor in values)
    assert start <= add_months(earliest, -2)
    assert all(row.demand_qty >= 0 for row in world.demand_signal_points + world.demand_signal_revisions)


@pytest.mark.parametrize("change", ["REDUCTION", "DELAY", "MIXED"])
def test_demand_adjustment_and_customer_side_evidence(evidence_demo, change):
    world, scenario, _, procurement, _, _, _, sc, _ = evidence_demo
    observation = DemandObservationIndex(world)
    signals = {(row.material_id, row.project_id): row for row in world.demand_signals}
    patterns = set()
    for mid, plan in scenario.material_scenario_plans.items():
        if plan.demand_change_type != change:
            continue
        patterns.add(plan.scenario_pattern)
        signal = signals[(mid, plan.causal_project_id)]
        for before, after, start in source_cycles(material_anchors(scenario, procurement)[mid]):
            metrics = shape_metrics(observation.observe(signal.demand_signal_id, before), observation.observe(signal.demand_signal_id, after), start, sc)
            if change == "REDUCTION":
                assert metrics["drop"] >= sc.reduction_total_drop_ratio
                assert metrics["shift"] == 0
            elif change == "DELAY":
                assert metrics["retention"] == 1
                assert metrics["shift"] >= sc.delay_shift_share_min
                assert metrics["near_drop"] >= sc.delay_near_term_drop_ratio
            else:
                assert metrics["drop"] >= sc.mixed_total_drop_ratio
                assert metrics["shift"] >= sc.mixed_shift_share_min
                assert metrics["retention"] < sc.delay_total_retention_lower
    assert "CUSTOMER_SIDE_PROJECT_OBSOLESCENCE" in patterns
    assert len(patterns) == 2


def test_after_sales_min_weeks_months_and_stockpile_both(evidence_demo):
    world, scenario, _, _, _, _, _, sc, snapshot = evidence_demo
    index = DemandObservationIndex(world)
    signals = {(r.material_id, r.project_id): r for r in world.demand_signals}
    flags = set()
    for mid, plan in scenario.material_scenario_plans.items():
        if plan.scenario_pattern == "AFTER_SALES":
            flags.add(plan.stockpile_flag)
            signal = signals[(mid, plan.causal_project_id)]
            stats = future_statistics(index.observe(signal.demand_signal_id, snapshot), snapshot, signal.reference_daily_qty)
            assert stats["weeks"] == 13 and stats["months"] == 6
            assert has_after_sales_quantities(stats, sc)
    assert flags == {True, False}


@pytest.mark.parametrize("pattern", ["STOCKPILE", "INTERNAL_SIDE_PROJECT_OBSOLESCENCE"])
def test_eol_negative_evidence(evidence_demo, pattern):
    world, scenario, _, _, _, _, _, sc, snapshot = evidence_demo
    index = DemandObservationIndex(world)
    signals = {(r.material_id, r.project_id): r for r in world.demand_signals}
    lifecycle_seen = set()
    for mid, plan in scenario.material_scenario_plans.items():
        if plan.scenario_pattern == pattern:
            lifecycle_seen.add(plan.lifecycle_state)
            signal = signals[(mid, plan.causal_project_id)]
            stats = future_statistics(index.observe(signal.demand_signal_id, snapshot), snapshot, signal.reference_daily_qty)
            assert not has_after_sales_quantities(stats, sc)
    assert lifecycle_seen <= {"MASS_PRODUCTION", "EOL"} and lifecycle_seen


def test_internal_eol_negative_evidence_in_alternate_scenario_world():
    scenario, master, procurement, dataset_id, signature, sc, snapshot = _scenario(20260829)
    assert any(plan.scenario_pattern == "INTERNAL_SIDE_PROJECT_OBSOLESCENCE" and plan.lifecycle_state == "EOL" for plan in scenario.material_scenario_plans.values())
    config = EvidenceFoundationConfig()
    world = EvidenceFoundationGenerator().generate(dataset_id, snapshot, signature, config, sc, master, procurement, scenario)
    EvidenceFoundationValidator().validate(world, master, procurement, scenario, dataset_id, snapshot, config, sc)


def test_multi_project_demand_world_and_causal_strength(evidence_demo):
    world, scenario, master, procurement, _, _, _, sc, snapshot = evidence_demo
    signals = {(r.material_id, r.project_id): r for r in world.demand_signals}
    assert set(signals) == {(r.material_id, r.project_id) for r in master.material_projects}
    index = DemandObservationIndex(world)
    checked = 0
    for mid, plan in scenario.material_scenario_plans.items():
        if plan.demand_change_type == "NONE":
            continue
        target = signals[(mid, plan.causal_project_id)]
        for before, after, start in source_cycles(material_anchors(scenario, procurement)[mid]):
            strength = shape_metrics(index.observe(target.demand_signal_id, before), index.observe(target.demand_signal_id, after), start, sc)["strength"]
            for (other_mid, pid), other in signals.items():
                if other_mid == mid and pid != plan.causal_project_id:
                    assert sum(index.observe(other.demand_signal_id, snapshot).values()) > 0
                    assert strength > shape_metrics(index.observe(other.demand_signal_id, before), index.observe(other.demand_signal_id, after), start, sc)["strength"]
                    checked += 1
    assert checked > 0


def test_evidence_foundation_determinism_and_seed_changes_noise():
    first, signature = small_evidence()
    same, same_signature = small_evidence()
    changed, changed_signature = small_evidence(seed=20260830)
    assert signature == same_signature
    assert first.content_hash(signature) == same.content_hash(same_signature)
    assert first.content_hash(signature) != changed.content_hash(changed_signature)
    assert [row.demand_qty for row in first.demand_signal_points] != [row.demand_qty for row in changed.demand_signal_points]
    assert [(row.project_id, row.lifecycle_stage) for row in first.project_lifecycle_history if row.lifecycle_stage == "EOL"]


def test_calendar_cross_year_and_leap_day():
    assert add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)
    world, _ = small_evidence(snapshot=date(2028, 2, 29))
    assert date(2028, 2, 29) in {row.demand_date for row in world.demand_signal_points}


def test_platform_truth_leakage():
    forbidden = {"true_cause", "scenario_pattern", "causal_project_id", "demand_change_type", "responsibility_type", "expected_action"}
    for model in EVIDENCE_MODELS:
        assert not forbidden.intersection(model.__table__.columns.keys())
    text = (Path(__file__).resolve().parents[1] / "app/models/platform/evidence_foundation.py").read_text(encoding="utf-8")
    assert "app.models.evaluation" not in text
    assert all(label not in text for label in ("REDUCTION", "DELAY", "MIXED", "AFTER_SALES"))


def test_quantity_observations_do_not_look_ahead(evidence_demo):
    world, scenario, _, procurement, _, _, _, sc, _ = evidence_demo
    index = DemandObservationIndex(world)
    plan = next(plan for plan in scenario.material_scenario_plans.values() if plan.demand_change_type == "REDUCTION")
    signal = next(row for row in world.demand_signals if (row.material_id, row.project_id) == (plan.material_id, plan.causal_project_id))
    before, after, start = source_cycles(material_anchors(scenario, procurement)[plan.material_id])[0]
    assert index.observe(signal.demand_signal_id, before) == index.observe(signal.demand_signal_id, after - timedelta(days=1))
    assert shape_metrics(index.observe(signal.demand_signal_id, before), index.observe(signal.demand_signal_id, after), start, sc)["drop"] > 0
