from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from random import Random

from app.core.ids import deterministic_uuid
from app.domain.procurement import is_overdue
from app.generators.config import GenerationConfig
from app.generators.context import GenerationContext
from app.generators.master_data.generator import MasterDataGenerator
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.generator import ProcurementGenerator
from app.generators.procurement.signature import procurement_generation_signature
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.mappings import MASS_PATTERNS, PATTERNS, PATTERN_CAUSE
from app.generators.scenarios.planner import ScenarioPlanner
from app.generators.scenarios.signature import scenario_generation_signature
from app.generators.scenarios.validation import ScenarioWorldValidator
from app.generators.scenarios.validation import ScenarioWorldValidationError
from app.generators.signature import generation_signature
from app.models.evaluation import ScenarioTruth
from sqlalchemy import UniqueConstraint
import pytest


def test_scenario_truth_schema_has_schedule_uniqueness_and_hidden_fields() -> None:
    table = ScenarioTruth.__table__
    assert table.schema == "evaluation"
    assert {
        "scenario_truth_id",
        "po_line_schedule_id",
        "po_line_id",
        "scenario_pattern",
        "true_cause",
        "true_cause_subtype",
        "causal_project_id",
        "demand_change_type",
        "lifecycle_state",
        "stockpile_flag",
        "responsibility_type",
        "expected_action",
    } <= set(table.columns.keys())
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("dataset_version_id", "po_line_schedule_id") in unique_sets


def _scenario(scenario_seed: int = 20260828, **config_overrides):
    master_config = GenerationConfig.demo()
    dataset_signature = generation_signature(master_config)
    dataset_id = deterministic_uuid(dataset_signature, "dataset_version", dataset_signature)
    master = MasterDataGenerator().generate(
        GenerationContext(
            dataset_id,
            dataset_signature,
            master_config,
            Random(master_config.random_seed),
        )
    )
    procurement_config = ProcurementGenerationConfig.demo()
    procurement_signature = procurement_generation_signature(
        dataset_signature, procurement_config
    )
    procurement = ProcurementGenerator().generate(
        dataset_id,
        master_config.snapshot_date,
        procurement_signature,
        procurement_config,
        master,
    )
    config = ScenarioGenerationConfig.demo(
        scenario_seed=scenario_seed, **config_overrides
    )
    signature = scenario_generation_signature(
        dataset_signature, procurement.procurement_facts_hash(), config
    )
    world = ScenarioPlanner().plan(
        dataset_id,
        master_config.snapshot_date,
        signature,
        config,
        master,
        procurement,
    )
    return world, master, procurement, dataset_id, signature, config, master_config.snapshot_date


def test_truth_only_for_overdue_and_one_truth_per_schedule() -> None:
    world, master, procurement, dataset_id, _, config, snapshot = _scenario()
    lines = {row.po_line_id: row for row in procurement.po_lines}
    overdue = {
        row.po_line_schedule_id
        for row in procurement.po_line_schedules
        if is_overdue(
            snapshot,
            lines[row.po_line_id].order_date,
            lines[row.po_line_id].material_lt_days_at_order,
        )
    }
    truth_ids = [row.po_line_schedule_id for row in world.scenario_truth_rows]
    assert set(truth_ids) == overdue
    assert len(truth_ids) == len(set(truth_ids))
    ScenarioWorldValidator().validate(
        world, master, procurement, dataset_id, snapshot, config
    )


def test_scenario_coverage_mapping_trial_priority_and_material_consistency() -> None:
    world, master, procurement, _, _, _, _ = _scenario()
    lines = {row.po_line_id: row for row in procurement.po_lines}
    headers = {row.po_header_id: row for row in procurement.po_headers}
    organizations = {row.organization_id: row for row in master.organizations}
    assert {row.scenario_pattern for row in world.scenario_truth_rows} == set(PATTERNS)
    assert all(row.true_cause == PATTERN_CAUSE[row.scenario_pattern] for row in world.scenario_truth_rows)
    for row in world.scenario_truth_rows:
        line = lines[row.po_line_id]
        header = headers[line.po_header_id]
        inventory_type = organizations[header.inventory_organization_id].inventory_organization_type
        assert (inventory_type == "TRIAL") == (row.scenario_pattern == "TRIAL")
    values_by_material = defaultdict(set)
    for row in world.scenario_truth_rows:
        material_id = lines[row.po_line_id].material_id
        values_by_material[material_id].add(
            (
                row.scenario_pattern,
                row.causal_project_id,
                row.demand_change_type,
                row.lifecycle_state,
                row.stockpile_flag,
            )
        )
    assert all(len(values) == 1 for values in values_by_material.values())


def test_causal_relationship_mismatch_lifecycle_and_stockpile_plans() -> None:
    world, master, procurement, _, _, _, _ = _scenario()
    lines = {row.po_line_id: row for row in procurement.po_lines}
    relationships = {
        (row.material_id, row.project_id) for row in master.material_projects
    }
    nontrial = [row for row in world.scenario_truth_rows if row.scenario_pattern != "TRIAL"]
    mismatch = sum(
        lines[row.po_line_id].po_reference_project_id != row.causal_project_id
        for row in nontrial
    )
    assert mismatch / len(nontrial) >= 0.15
    assert all(
        (lines[row.po_line_id].material_id, row.causal_project_id) in relationships
        for row in world.scenario_truth_rows
    )
    lifecycle_by_project = defaultdict(set)
    for row in world.scenario_truth_rows:
        lifecycle_by_project[row.causal_project_id].add(row.lifecycle_state)
    assert all(len(states) == 1 for states in lifecycle_by_project.values())
    assert all(
        row.stockpile_flag
        for row in world.scenario_truth_rows
        if row.scenario_pattern == "STOCKPILE"
    )
    assert all(
        not row.stockpile_flag
        for row in world.scenario_truth_rows
        if row.scenario_pattern == "INTERNAL_SIDE_PROJECT_OBSOLESCENCE"
    )
    assert {
        row.stockpile_flag
        for row in world.scenario_truth_rows
        if row.scenario_pattern == "AFTER_SALES"
    } == {True, False}


def test_determinism_and_seed_changes_scenario_plan() -> None:
    first, _, _, _, signature, _, _ = _scenario()
    second, _, _, _, _, _, _ = _scenario()
    changed, _, _, _, changed_signature, _, _ = _scenario(20260829)
    assert first.scenario_content_hash(signature) == second.scenario_content_hash(signature)
    assert [row.scenario_truth_id for row in first.scenario_truth_rows] == [
        row.scenario_truth_id for row in second.scenario_truth_rows
    ]
    assert first.scenario_content_hash(signature) != changed.scenario_content_hash(
        changed_signature
    )
    assert first.material_scenario_plans != changed.material_scenario_plans


@pytest.mark.parametrize("weighted_pattern", MASS_PATTERNS)
def test_coverage_first_survives_zero_weights(weighted_pattern: str) -> None:
    weights = {
        pattern: Decimal(1 if pattern == weighted_pattern else 0)
        for pattern in MASS_PATTERNS
    }
    world, master, procurement, dataset_id, signature, config, snapshot = _scenario(
        mass_pattern_weights=weights
    )
    ScenarioWorldValidator().validate(
        world, master, procurement, dataset_id, snapshot, config
    )
    assert set(Counter(row.scenario_pattern for row in world.scenario_truth_rows)) == set(PATTERNS)
    after_sales = [
        row for row in world.scenario_truth_rows if row.scenario_pattern == "AFTER_SALES"
    ]
    assert {row.stockpile_flag for row in after_sales} == {True, False}
    assert all(row.expected_action is None for row in after_sales)
    repeated, _, _, _, repeated_signature, _, _ = _scenario(mass_pattern_weights=weights)
    assert world.scenario_content_hash(signature) == repeated.scenario_content_hash(
        repeated_signature
    )


def test_negative_pattern_weight_is_rejected_even_when_total_is_one() -> None:
    weights = dict.fromkeys(MASS_PATTERNS, Decimal(0))
    weights[MASS_PATTERNS[0]] = Decimal("-1")
    weights[MASS_PATTERNS[1]] = Decimal("2")
    with pytest.raises(ValueError, match="nonnegative"):
        ScenarioGenerationConfig.demo(mass_pattern_weights=weights)


def test_validator_rejects_project_lifecycle_conflict() -> None:
    world, master, procurement, dataset_id, _, config, snapshot = _scenario()
    by_project = defaultdict(list)
    for row in world.scenario_truth_rows:
        by_project[row.causal_project_id].append(row)
    rows = next(values for values in by_project.values() if len(values) > 1)
    rows[0].lifecycle_state = (
        "EOL" if rows[0].lifecycle_state == "MASS_PRODUCTION" else "MASS_PRODUCTION"
    )
    with pytest.raises(ScenarioWorldValidationError, match="conflicting lifecycle"):
        ScenarioWorldValidator().validate(
            world, master, procurement, dataset_id, snapshot, config
        )


def test_mock_threshold_defaults_are_explicit() -> None:
    config = ScenarioGenerationConfig.demo()
    assert config.comparison_months == 7
    assert str(config.reduction_total_drop_ratio) == "0.35"
    assert config.delay_near_term_months == 3
    assert str(config.after_sales_level_ratio_min) == "0.05"
    assert config.after_sales_min_nonzero_weeks == 8
    assert str(config.forecast_rounding_tolerance) == "0.01"


@pytest.mark.parametrize(
    ("field", "default", "changed"),
    [
        ("comparison_months", 7, 6),
        ("reduction_total_drop_ratio", "0.35", "0.40"),
        ("delay_near_term_months", 3, 2),
        ("delay_near_term_drop_ratio", "0.30", "0.40"),
        ("delay_total_retention_lower", "0.85", "0.80"),
        ("delay_total_retention_upper", "1.15", "1.20"),
        ("delay_shift_share_min", "0.30", "0.40"),
        ("mixed_total_drop_ratio", "0.20", "0.30"),
        ("mixed_shift_share_min", "0.20", "0.30"),
        ("after_sales_level_ratio_min", "0.05", "0.06"),
        ("after_sales_level_ratio_max", "0.20", "0.25"),
        ("after_sales_min_nonzero_weeks", 8, 9),
        ("after_sales_min_nonzero_months", 4, 5),
        ("forecast_rounding_tolerance", "0.01", "0.02"),
    ],
)
def test_mock_thresholds_are_configurable_and_signed(field, default, changed) -> None:
    config = ScenarioGenerationConfig.demo()
    assert str(getattr(config, field)) == str(default)
    changed_config = ScenarioGenerationConfig.demo(**{field: changed})
    assert str(getattr(changed_config, field)) == str(changed)
    assert scenario_generation_signature("dataset", "facts", config) != (
        scenario_generation_signature("dataset", "facts", changed_config)
    )


@pytest.mark.parametrize(
    "filename",
    ["DATA_CONTRACT.md", "SCENARIO_RULES.md", "DB_SCHEMA.md", "ARCHITECTURE_API.md", "ACCEPTANCE_TESTS.md"],
)
def test_business_confirmation_status_stays_consistent(filename: str) -> None:
    document = Path(__file__).resolve().parents[2] / "docs" / filename
    lines = document.read_text(encoding="utf-8").splitlines()
    dc15_lines = [line for line in lines if "`DC-15`" in line]
    assert any("RESOLVED_AS_SYNTHETIC_CONFIG" in line for line in dc15_lines)
    assert not any("DEFERRED_TO_GENERATOR" in line for line in dc15_lines)
    assert any(
        "DC-16" in line and ("NEEDS_BUSINESS_CONFIRMATION" in line or "仍 blocked" in line)
        for line in lines
    )
