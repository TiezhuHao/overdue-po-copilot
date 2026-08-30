"""Decision golden cases use fixed canonical evidence, never live services."""
import ast
from datetime import date
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.system_b.decision.engine import decide, DecisionInputError
from app.system_b.decision.models import (
    BusinessDecisionPolicy, CONFIRMED_CONSUMPTION_POLICY, DecisionContext,
)
from app.system_b.diagnosis.assembler import assemble_evidence, EvidenceAssemblyError
from app.system_b.diagnosis.policy import diagnose_business
from tests.test_system_b_diagnosis_completion import facts, policy, GOLDEN
from tests.test_system_b_diagnosis import po, full_inputs


def context(inputs=None, decision_policy=CONFIRMED_CONSUMPTION_POLICY):
    bundle = assemble_evidence(inputs if inputs is not None else facts())
    return DecisionContext(diagnosis=diagnose_business(bundle, policy()), evidence=bundle, policy=decision_policy)


EXPECTED = {
    "trial": ("REQUEST_MPM_CONFIRMATION", "MPM"),
    "customer": ("COMMUNICATE_CUSTOMER_OBSOLESCENCE", "CUSTOMER"),
    "demand": ("CONTINUE_CONSUMPTION", None),
    "timing_shift": ("CONTINUE_CONSUMPTION", None),
    "after_sales": (None, None),
    "stockpile": ("CONTINUE_CONSUMPTION", None),
    "internal": ("COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE", "BUSINESS_UNIT"),
    "eol_stockpile": ("CONTINUE_CONSUMPTION", None),
    "eol_internal": ("COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE", "BUSINESS_UNIT"),
}


@pytest.mark.parametrize("name,values,reason,rule", GOLDEN, ids=[row[0] for row in GOLDEN])
def test_golden_actions(name, values, reason, rule):
    ctx = context(facts(**values))
    result = decide(ctx)
    code, owner = EXPECTED[name]
    assert result.source_diagnosis.primary_reason == reason
    assert result.source_diagnosis.primary_rule_id == rule
    assert result.decision_rule_id == rule.replace("business_", "decision_")
    assert result.decision_rule_version == "1.0.0"
    assert result.owner_role == owner
    assert result.source_diagnosis == ctx.diagnosis
    if code is None:
        assert result.decision_status == "NOT_EVALUABLE" and not result.actions
        assert [(gap.code, gap.requirement) for gap in result.unresolved_requirements] == [("DECISION_SPEC_GAP", "DC-16")]
    else:
        assert result.decision_status == "DECIDED"
        assert [action.action_code for action in result.actions] == [code]
        assert result.actions[0].required


@pytest.mark.parametrize("branch", ["demand", "stockpile"])
@pytest.mark.parametrize("qty,action", [("77.9999999999999999999999999999", "CONTINUE_CONSUMPTION"),
    ("78", "NEGOTIATE_SUPPLIER_ORDER_REDUCTION"), ("78.0000000000000000000000000001", "NEGOTIATE_SUPPLIER_ORDER_REDUCTION")])
def test_six_month_boundary(branch, qty, action):
    inputs = facts("reduction" if branch == "demand" else "stable", lifecycle="MASS_PRODUCTION",
                   po=po(schedule_qty=Decimal(qty), schedule_received_qty=Decimal(0), overdue_open_qty=Decimal(qty)))
    result = decide(context(inputs))
    assert result.actions[0].action_code == action
    if qty == "78":
        assert result.estimated_consumption_months == Decimal(6)
    assert result.decision_policy.threshold_months == Decimal(6) and result.policy_fingerprint
    assert result.used_policy_fields == ("threshold_months",)
    if action == "CONTINUE_CONSUMPTION":
        assert result.owner_role is None
        assert [(gap.requirement, gap.blocking) for gap in result.unresolved_requirements] == [("CONSUMPTION_OWNER", False)]
    else:
        assert result.owner_role == "SUPPLIER" and not result.unresolved_requirements


@pytest.mark.parametrize("provided", [None, BusinessDecisionPolicy()])
def test_missing_consumption_policy_blocks_actions(provided):
    result = decide(context(facts(lifecycle="MASS_PRODUCTION"), provided))
    assert result.decision_status == "NOT_EVALUABLE" and not result.actions
    assert any(gap.code == "MISSING_POLICY_PARAMETER" for gap in result.unresolved_requirements)


@pytest.mark.parametrize("qty", ["5", "26", "NaN", "Infinity", "-1"])
def test_no_unconfirmed_threshold_override(qty):
    with pytest.raises(ValidationError):
        BusinessDecisionPolicy(threshold_months=qty)


@pytest.mark.parametrize("mode", ["missing_supply", "missing_employee_id"])
def test_trial_missing_mpm_does_not_invent_contact(mode):
    inputs = full_inputs(po=po(inventory_organization_type="TRIAL"), weekly=None, products=())
    supply = None if mode == "missing_supply" else inputs.supply.model_copy(
        update={"mpm": inputs.supply.mpm.model_copy(update={"employee_id": None})})
    ctx = context(inputs.model_copy(update={"supply": supply}), None)
    assert ctx.diagnosis.status == "DIAGNOSED"
    result = decide(ctx)
    assert result.decision_status == "NOT_EVALUABLE" and result.owner_role == "MPM" and not result.actions


def test_trial_requires_neither_project_nor_forecast_nor_consumption_policy():
    inputs = full_inputs(po=po(inventory_organization_type="TRIAL", po_reference_project_id=None), weekly=None,
                         products=(), forecast_history=None, previous_forecast=None, current_forecast=None, stockpile=None)
    result = decide(context(inputs, None))
    action = result.actions[0]
    assert action.mpm_contact == inputs.supply.mpm
    trace = {fact.evidence_id: fact for fact in result.evidence_trace}
    assert "mpm.employee_id" in action.evidence_refs
    assert {key.name for key in trace["mpm.employee_id"].entity_keys} >= {"material_id", "employee_id"}
    assert "project_id" not in {key.name for key in trace["mpm.employee_id"].entity_keys}
    assert result.used_policy_fields == ()


def test_zero_open_quantity_has_zero_period_not_unknown():
    result = decide(context(facts(lifecycle="MASS_PRODUCTION", po=po(overdue_open_qty=Decimal(0)))))
    assert result.estimated_consumption_months == 0
    assert result.actions[0].action_code == "CONTINUE_CONSUMPTION"


def test_same_primary_reason_routes_to_different_counterparts_without_policy():
    customer = decide(context(facts("reduction"), None))
    internal = decide(context(facts(lifecycle="MASS_PRODUCTION", tag="OTHER"), None))
    assert customer.source_diagnosis.primary_reason == internal.source_diagnosis.primary_reason
    assert customer.decision_rule_id != internal.decision_rule_id
    assert customer.actions[0].action_code != internal.actions[0].action_code
    assert customer.owner_role == "CUSTOMER" and internal.owner_role == "BUSINESS_UNIT"


@pytest.mark.parametrize("mode", ["missing", "partial", "zero"])
def test_unresolved_forecast_never_bypasses_diagnosis(mode):
    inputs = facts(first_qty="0", second_qty="0") if mode == "zero" else facts()
    if mode != "zero":
        inputs = inputs.model_copy(update={"weekly": None if mode == "missing" else inputs.weekly.model_copy(
            update={"weeks": (inputs.weekly.weeks[0].model_copy(update={"week_start_date": None}),
                              *inputs.weekly.weeks[1:]), "project_contributions": None})})
    result = decide(context(inputs))
    assert result.source_diagnosis.status == "UNRESOLVED"
    assert result.decision_status == "NOT_EVALUABLE" and not result.actions
    assert result.unresolved_requirements[0].code == "DIAGNOSIS_UNRESOLVED"


def test_not_eligible_has_no_actions():
    inputs = full_inputs(po=po(order_date=date(2026, 1, 1), inventory_organization_type="TRIAL"),
                         stockpile=None, forecast_history=None)
    result = decide(context(inputs))
    assert result.source_diagnosis.status == "NOT_ELIGIBLE"
    assert result.decision_status == "NOT_APPLICABLE" and not result.actions


def test_negative_quantity_blocks_consumption_even_with_primary_diagnosis():
    result = decide(context(facts(lifecycle="MASS_PRODUCTION", po=po(overdue_open_qty=Decimal(-1)))))
    assert result.source_diagnosis.status == "DIAGNOSED"
    assert result.decision_status == "NOT_EVALUABLE" and not result.actions
    assert any(gap.requirement == "PO_CONSUMPTION" for gap in result.unresolved_requirements)


@pytest.mark.parametrize("mode", ["rule_version", "routing_version", "rule_id"])
def test_unsupported_source_never_falls_back_by_reason(mode):
    ctx = context(facts("reduction"))
    diagnosis = ctx.diagnosis
    changes = {"routing_policy_version": "future"}
    if mode != "routing_version":
        key = "rule_version" if mode == "rule_version" else "rule_id"
        evaluations = tuple(item.model_copy(update={key: "future"}) if item.rule_id == diagnosis.primary_rule_id else item
                            for item in diagnosis.business_evaluations)
        changes = {"primary_" + key: "future", "business_evaluations": evaluations}
    result = decide(ctx.model_copy(update={"diagnosis": diagnosis.model_copy(update=changes)}))
    assert result.decision_status == "NOT_EVALUABLE" and not result.actions
    assert result.unresolved_requirements[0].code == "UNSUPPORTED_DIAGNOSIS_RULE"


@pytest.mark.parametrize("mode", ["scope", "trace", "parents", "policy", "metric"])
def test_rejects_stale_or_forged_lineage(mode):
    ctx = context(facts("reduction"))
    diagnosis = ctx.diagnosis
    if mode == "scope":
        diagnosis = diagnosis.model_copy(update={"dataset_version_id": UUID(int=999)})
    elif mode == "trace":
        trace = list(diagnosis.evidence_trace)
        trace[0] = trace[0].model_copy(update={"observed_value": "forged"})
        diagnosis = diagnosis.model_copy(update={"evidence_trace": tuple(trace)})
    elif mode == "parents":
        diagnosis = diagnosis.model_copy(update={"evidence_trace": diagnosis.evidence_trace[1:]})
    elif mode == "policy":
        diagnosis = diagnosis.model_copy(update={"policy_fingerprint": "forged"})
    else:
        analytics = ctx.evidence.analytics
        analytics = analytics.model_copy(update={"consumption": analytics.consumption.model_copy(
            update={"estimated_consumption_weeks": Decimal(999)})})
        ctx = ctx.model_copy(update={"evidence": ctx.evidence.model_copy(update={"analytics": analytics})})
    with pytest.raises((DecisionInputError, EvidenceAssemblyError)):
        decide(ctx.model_copy(update={"diagnosis": diagnosis}))


def test_determinism_trace_closure_and_no_rediagnosis(monkeypatch):
    ctx = context(facts(lifecycle="MASS_PRODUCTION"))
    original = ctx.model_dump_json()

    def forbidden(*args, **kwargs):
        raise AssertionError("Decision must not re-diagnose")

    monkeypatch.setattr("app.system_b.diagnosis.policy.diagnose_business", forbidden)
    monkeypatch.setattr("app.system_b.diagnosis.engine.diagnose", forbidden)
    first = decide(ctx)
    with localcontext() as ambient:
        ambient.prec, ambient.rounding = 5, ROUND_UP
        ambient.traps[Inexact] = True
        flags = dict(ambient.flags)
        second = decide(ctx)
        assert ambient.prec == 5 and ambient.rounding == ROUND_UP and dict(ambient.flags) == flags
    assert second.model_dump_json() == first.model_dump_json()
    assert ctx.model_dump_json() == original
    trace = {fact.evidence_id: fact for fact in first.evidence_trace}
    assert "consumption.estimated_consumption_weeks" in first.actions[0].evidence_refs
    assert all(set(fact.derived_from) <= trace.keys() for fact in trace.values())
    assert all(set(action.evidence_refs) <= trace.keys() for action in first.actions)
    assert first.source_diagnosis.policy_fingerprint == ctx.diagnosis.policy_fingerprint


def test_decision_import_boundary():
    root = Path(__file__).resolve().parents[1] / "app" / "system_b" / "decision"
    banned = ("httpx", "requests", "sqlalchemy", "app.repositories", "app.generator", "langgraph", "openai")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        names += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(name.startswith(banned) for name in names)
