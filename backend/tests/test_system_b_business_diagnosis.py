"""Golden facts test actual rules; synthetic evaluations test policy selection only."""
import ast
import json
from datetime import timedelta
from decimal import Inexact, ROUND_UP, localcontext
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.system_b.diagnosis.assembler import assemble_evidence, EvidenceAssemblyError
from app.system_b.diagnosis.business_models import BusinessDiagnosisResult, BusinessRuleEvaluation, BusinessStatus as B, DiagnosisCode
from app.system_b.diagnosis.business_rules import BUSINESS_RULES
from app.system_b.diagnosis.models import Completeness, EvidenceInputs, EvidenceKind as K, RuleState as S, SignalCode
from app.system_b.diagnosis.policy import diagnose_business, select_primary
from tests.test_system_b_diagnosis import full_inputs, po, product, SNAPSHOT


CASES = json.loads((Path(__file__).parent / "fixtures/diagnosis_scenarios/business_cases.json").read_text(encoding="utf-8"))


def scenario_inputs(case):
    item = po(inventory_organization_type=case["organization"])
    if "delta" in case:
        item = item.model_copy(update={"order_date": SNAPSHOT - timedelta(days=item.material_lt_days + 240 + case["delta"])})
    if case["profile"] == "minimal":
        return EvidenceInputs(po=item)
    inputs = full_inputs(po=item)
    if "delta" in case:
        # A different order date needs a different historical query; do not invent one.
        inputs = inputs.model_copy(update={"stockpile": None})
    if "lifecycle" in case:
        inputs = inputs.model_copy(update={"products": (product(lifecycle_stage=case["lifecycle"]),)})
    return inputs


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_golden_business_scenarios(case):
    result = diagnose_business(assemble_evidence(scenario_inputs(case)))
    assert result.status == case["status"]
    assert result.primary_reason == case["primary"] and result.primary_rule_id == case["rule"]
    assert result.primary_rule_version == ("1.0.0" if case["primary"] else None)
    assert result.as_of_date == SNAPSHOT
    if case["primary"]:
        assert result.completeness == Completeness.COMPLETE and result.rule_gaps == ()
        assert [item.state for item in result.business_evaluations] == [S.MATCHED] + [S.NOT_MATCHED] * 5
        assert all(item.reason_summary_code == "EXCLUDED_BY_TRIAL" for item in result.business_evaluations[1:])
    elif result.status == B.UNRESOLVED:
        assert result.rule_gaps and result.completeness == Completeness.PARTIAL
        assert result.business_evaluations[0].state == S.NOT_MATCHED
        assert all(item.state == S.NOT_EVALUABLE for item in result.business_evaluations[1:])
    else:
        assert all(item.reason_summary_code == "PO_NOT_ELIGIBLE" for item in result.business_evaluations)


def test_supporting_signals_never_compete_for_primary_or_block_trial():
    result = diagnose_business(assemble_evidence(full_inputs(po=po(inventory_organization_type="TRIAL"))))
    assert result.primary_reason == DiagnosisCode.TRIAL
    assert SignalCode.NEGATIVE_FORECAST_CHANGE in result.signals
    assert SignalCode.HISTORICAL_STOCKPILE_RECORD_PRESENT in result.signals
    assert result.suppressed_matches == ()  # These signals are not competing business matches.
    minimal = diagnose_business(assemble_evidence(EvidenceInputs(po=po(inventory_organization_type="TRIAL"))))
    assert minimal.primary_reason == DiagnosisCode.TRIAL
    assert minimal.evaluations[1].state == S.NOT_EVALUABLE  # missing optional signal retained
    assert minimal.missing_evidence == () and minimal.completeness == Completeness.COMPLETE


@pytest.mark.parametrize("organization", ["", "UNKNOWN", "NPI", "trial"])
def test_unknown_organization_is_not_silently_treated_as_mass(organization):
    result = diagnose_business(assemble_evidence(EvidenceInputs(po=po(inventory_organization_type=organization))))
    assert result.status == B.UNRESOLVED and result.primary_reason is None
    assert all(item.state == S.NOT_EVALUABLE for item in result.business_evaluations)
    assert all(item.reason_summary_code == "UNSUPPORTED_ORGANIZATION_TYPE" for item in result.business_evaluations)
    assert result.missing_evidence[0].fields == ("inventory_organization_type",)


@pytest.mark.parametrize("change", [{"po_line_schedule_id": None}, {"material_id": None}, {"order_date": SNAPSHOT + timedelta(days=1)}])
def test_trial_cannot_bypass_missing_identity_or_invalid_aging(change):
    result = diagnose_business(assemble_evidence(EvidenceInputs(po=po(inventory_organization_type="TRIAL", **change))))
    assert result.status == B.UNRESOLVED and result.primary_reason is None
    assert all(item.state == S.NOT_EVALUABLE for item in result.business_evaluations)
    assert result.missing_evidence


def test_primary_provenance_contains_organization_aging_and_source_inputs():
    bundle = assemble_evidence(EvidenceInputs(po=po(inventory_organization_type="TRIAL")))
    result = diagnose_business(bundle)
    facts = {fact.evidence_id: fact for fact in result.evidence_trace}
    rule = result.business_evaluations[0]
    assert rule.used_evidence_ids == ("aging.threshold_delta_days", "po.inventory_organization_type")
    org = facts["po.inventory_organization_type"]
    assert org.source == "R1" and org.observed_value == "TRIAL" and org.snapshot_date == SNAPSHOT
    assert org.dataset_version_id == bundle.inputs.po.dataset_version_id
    assert {key.name: key.value for key in org.entity_keys}["organization_id"] == bundle.inputs.po.organization_id
    assert facts["aging.threshold_delta_days"].derived_from == ("po.order_date", "po.material_lt_days")
    assert "po.order_date" in facts and "po.material_lt_days" in facts
    assert result.policy_id == "procurement_diagnosis" and result.policy_version == "1.0.0"


def test_rule_gaps_remain_even_when_all_foundation_signals_are_available():
    result = diagnose_business(assemble_evidence(full_inputs()))
    assert result.status == B.UNRESOLVED and result.primary_reason is None
    assert {gap.gap_id for gap in result.rule_gaps} == {
        "SIGNIFICANT_FORECAST_CHANGE", "MOST_LIKELY_PROJECT_SELECTION", "ANCHOR_COMPARISON_WINDOW",
        "AFTER_SALES_PATTERN", "VALID_STOCKPILE_CONDITION",
    }
    assert {gap.code for gap in result.rule_gaps} == {"RULE_SPEC_GAP", "CONTRACT_GAP"}


def test_policy_catalog_preserves_confirmed_branch_order_and_five_causes():
    assert [(rule.rule_id, rule.priority) for rule in BUSINESS_RULES] == [
        ("business_trial", 10), ("business_customer_obsolescence", 20), ("business_demand_adjustment", 20),
        ("business_after_sales", 30), ("business_stockpile", 40), ("business_internal_obsolescence", 50),
    ]
    assert set(DiagnosisCode) == {"TRIAL", "STOCKPILE", "DEMAND_ADJUSTMENT", "AFTER_SALES", "PROJECT_OBSOLESCENCE"}
    assert all(rule.version == "1.0.0" for rule in BUSINESS_RULES)


def policy_item(rule_id, priority, state):
    # Selector-only test values are not evidence fixtures or implemented cause rules.
    return BusinessRuleEvaluation(rule_id=rule_id, rule_version="selector-test", diagnosis_code=DiagnosisCode.TRIAL,
                                  priority=priority, state=state, reason_summary_code="TEST_ONLY")


def test_policy_multiple_matches_are_selected_by_explicit_rank_not_input_order():
    high, low = policy_item("high", 10, S.MATCHED), policy_item("low", 40, S.MATCHED)
    assert select_primary((high, low)) == select_primary((low, high)) == (high, B.DIAGNOSED, "PRIMARY_RULE_MATCHED")


@pytest.mark.parametrize("priority", [10, 20])
def test_unknown_higher_or_equal_priority_cannot_be_treated_as_excluded(priority):
    selected, status, summary = select_primary((policy_item("unknown", priority, S.NOT_EVALUABLE), policy_item("match", 20, S.MATCHED)))
    assert selected is None and status == B.UNRESOLVED and summary == "HIGHER_OR_EQUAL_PRIORITY_UNRESOLVED"


def test_policy_distinguishes_tie_missing_and_no_match():
    assert select_primary((policy_item("a", 20, S.MATCHED), policy_item("b", 20, S.MATCHED)))[2] == "CONFLICTING_RULE_MATCHES"
    assert select_primary((policy_item("a", 20, S.NOT_MATCHED),))[1] == B.NO_MATCH
    assert select_primary((policy_item("a", 20, S.NOT_EVALUABLE),))[1] == B.UNRESOLVED
    with pytest.raises(ValueError, match="INVALID_BUSINESS_EVALUATIONS"):
        select_primary(())


def test_current_lifecycle_reference_and_contribution_do_not_create_primary():
    inputs = full_inputs(po=po(po_reference_project_id=UUID(int=999)))
    bundle = assemble_evidence(inputs)
    assert bundle.fact_ids(K.CURRENT_LIFECYCLE)
    result = diagnose_business(bundle)
    assert result.primary_reason is None and result.status == B.UNRESOLVED
    assert bundle.missing_for((K.HISTORICAL_LIFECYCLE,))
    rendered = result.model_dump_json()
    assert all(field not in rendered for field in ("responsible_project", "root_cause_project", "demand_owner",
                                                  "recommended_action", "call_mpm", "cancel_po", "reschedule_po", "confidence"))


def test_business_result_and_trace_determinism_with_hostile_decimal_context():
    bundle = assemble_evidence(full_inputs(po=po(inventory_organization_type="TRIAL")))
    expected = diagnose_business(bundle).model_dump_json()
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        assert diagnose_business(bundle).model_dump_json() == expected
    assert diagnose_business(bundle).model_dump_json() == expected


def test_business_entry_preserves_bundle_validation_and_result_constraints():
    bundle = assemble_evidence(full_inputs())
    with pytest.raises(EvidenceAssemblyError, match="BUNDLE_DERIVATION_MISMATCH"):
        diagnose_business(bundle.model_copy(update={"facts": ()}))
    payload = diagnose_business(bundle).model_dump()
    with pytest.raises(ValidationError, match="PRIMARY_WITHOUT_DIAGNOSIS"):
        BusinessDiagnosisResult.model_validate(payload | {"primary_reason": "TRIAL"})
    with pytest.raises(ValidationError):
        BusinessDiagnosisResult.model_validate(payload | {"recommended_action": "test"})


def test_diagnosis_does_not_import_generator_thresholds_truth_or_io():
    root = Path(__file__).parents[1] / "app/system_b/diagnosis"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("app.generators", "app.evaluation", "app.models", "app.db",
                    "app.repositories", "app.services", "app.system_b.adapters", "httpx", "sqlalchemy", "openai", "langgraph"))
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in {"scenario_truth", "causal_project_id", "expected_action"}
