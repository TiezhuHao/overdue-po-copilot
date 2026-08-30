"""Validate evidence lineage and map the supplied primary diagnosis; no I/O."""
from decimal import Context, ROUND_HALF_EVEN, localcontext
from hashlib import sha256

from app.system_b.analytics.models import Availability, ReasonCode
from app.system_b.diagnosis.assembler import assemble_evidence, entity_keys
from app.system_b.diagnosis.business_models import BusinessStatus
from app.system_b.decision.models import (
    ActionCode as A, DecisionAction, DecisionContext, DecisionResult, DecisionStatus as S,
    OwnerRole as O, RequiredCheck, UnresolvedRequirement,
)
from app.system_b.decision.rules import DECISION_RULES


class DecisionInputError(ValueError):
    """Malformed/stale lineage is an input error, not a business conclusion."""


def _fingerprint(policy):
    return sha256(policy.model_dump_json().encode()).hexdigest() if policy is not None else None


def _validate(context):
    context = DecisionContext.model_validate(context.model_dump())
    diagnosis, bundle = context.diagnosis, context.evidence
    # Rebuild deterministic facts only; never call diagnose/select_primary/rules.
    if assemble_evidence(bundle.inputs) != bundle:
        raise DecisionInputError("BUNDLE_DERIVATION_MISMATCH")
    po = bundle.inputs.po
    if (diagnosis.dataset_version_id != po.dataset_version_id or diagnosis.as_of_date != po.snapshot_date
            or diagnosis.entity_keys != entity_keys(po)):
        raise DecisionInputError("DIAGNOSIS_SCOPE_MISMATCH")
    if diagnosis.policy_fingerprint != _fingerprint(diagnosis.business_policy):
        raise DecisionInputError("DIAGNOSIS_POLICY_MISMATCH")
    if diagnosis.business_policy is not None and (
        diagnosis.policy_id != diagnosis.business_policy.policy_id or diagnosis.policy_version != diagnosis.business_policy.version
    ):
        raise DecisionInputError("DIAGNOSIS_POLICY_MISMATCH")
    facts = {fact.evidence_id: fact for fact in bundle.facts}
    trace = {fact.evidence_id: fact for fact in diagnosis.evidence_trace}
    if len(trace) != len(diagnosis.evidence_trace) or any(facts.get(key) != value for key, value in trace.items()):
        raise DecisionInputError("DIAGNOSIS_TRACE_MISMATCH")
    used = {address for evaluation in (*diagnosis.evaluations, *diagnosis.business_evaluations)
            for address in evaluation.used_evidence_ids}
    parents = {address for fact in trace.values() for address in fact.derived_from}
    if not (used | parents) <= trace.keys() or (diagnosis.status == BusinessStatus.DIAGNOSED and not used):
        raise DecisionInputError("INCOMPLETE_DIAGNOSIS_TRACE")
    if diagnosis.status == BusinessStatus.DIAGNOSED and not next(
        item for item in diagnosis.business_evaluations if item.rule_id == diagnosis.primary_rule_id
    ).used_evidence_ids:
        raise DecisionInputError("EMPTY_PRIMARY_DIAGNOSIS_TRACE")
    return context


def decide(context: DecisionContext) -> DecisionResult:
    # Isolate validation as well as arithmetic: Decimal unions may set flags.
    with localcontext(Context(prec=40, rounding=ROUND_HALF_EVEN)):
        return _decide(context)


def _decide(context: DecisionContext) -> DecisionResult:
    context = _validate(context)
    diagnosis, bundle = context.diagnosis, context.evidence
    checks = [RequiredCheck(code="SOURCE_DIAGNOSIS_VALID", passed=True,
                            evidence_refs=tuple(fact.evidence_id for fact in diagnosis.evidence_trace))]
    gaps = []
    selected = {fact.evidence_id for fact in diagnosis.evidence_trace}
    rule, months, contact = None, None, None
    owner, action = None, None

    def gap(code, requirement, source, blocking=True):
        gaps.append(UnresolvedRequirement(code=code, requirement=requirement, source=source, blocking=blocking))

    def finish(status):
        by_id = {fact.evidence_id: fact for fact in bundle.facts}

        def include(address):
            for parent in by_id[address].derived_from:
                if parent not in selected:
                    selected.add(parent)
                    include(parent)

        for address in tuple(selected):
            include(address)
        trace = tuple(fact for fact in bundle.facts if fact.evidence_id in selected)
        actions = () if action is None else (DecisionAction(
            action_code=action, owner_role=owner, priority=rule.priority,
            evidence_refs=tuple(fact.evidence_id for fact in trace), decision_rule_id=rule.rule_id,
            decision_rule_version=rule.version, mpm_contact=contact),)
        return DecisionResult(decision_status=status, decision_rule_id=rule.rule_id if rule else None,
            decision_rule_version=rule.version if rule else None, source_diagnosis=diagnosis,
            decision_policy=context.policy, policy_fingerprint=_fingerprint(context.policy), owner_role=owner,
            used_policy_fields=("threshold_months",) if months is not None else (),
            actions=actions, required_checks=tuple(checks), unresolved_requirements=tuple(gaps),
            evidence_trace=trace, estimated_consumption_months=months)

    if diagnosis.status == BusinessStatus.NOT_ELIGIBLE:
        return finish(S.NOT_APPLICABLE)
    if diagnosis.status != BusinessStatus.DIAGNOSED:
        gap("DIAGNOSIS_UNRESOLVED", diagnosis.status.value, "source_diagnosis")
        return finish(S.NOT_EVALUABLE)
    rule = next((rule for rule in DECISION_RULES if (
        rule.diagnosis_code, rule.diagnosis_rule_id, rule.diagnosis_rule_version
    ) == (diagnosis.primary_reason, diagnosis.primary_rule_id, diagnosis.primary_rule_version)), None)
    if rule is None or diagnosis.routing_policy_version != "2.0.0":
        gap("UNSUPPORTED_DIAGNOSIS_RULE", "primary_rule_or_routing_version", "decision-rule-specification")
        return finish(S.NOT_EVALUABLE)

    owner = rule.owner_role
    missing = bundle.missing_for(rule.required_evidence)
    for kind in rule.required_evidence:
        refs = bundle.fact_ids(kind)
        selected.update(refs)
        passed = not any(item.kind == kind for item in missing) and bool(refs)
        code = "CONSUMPTION_AVAILABLE" if rule.consumption_based else "MATERIAL_MPM_AVAILABLE"
        checks.append(RequiredCheck(code=code, passed=passed, evidence_refs=refs))
        if not passed:
            gap("MISSING_REQUIRED_EVIDENCE", kind.value, rule.source)

    if rule.consumption_based:
        metric = bundle.analytics.consumption
        valid_policy = context.policy is not None and context.policy.threshold_months is not None
        checks.append(RequiredCheck(code="CONSUMPTION_POLICY_AVAILABLE", passed=valid_policy))
        if not valid_policy:
            gap("MISSING_POLICY_PARAMETER", "threshold_months", rule.source)
        if ReasonCode.NO_FORECAST_DEMAND in metric.reason_codes:
            gap("DECISION_SPEC_GAP", "ZERO_FORECAST_ACTION", "SCENARIO_RULES §7/§12")
        if gaps:
            return finish(S.NOT_EVALUABLE)
        if metric.status != Availability.AVAILABLE or metric.estimated_consumption_weeks is None:
            raise DecisionInputError("INCONSISTENT_CONSUMPTION_EVIDENCE")
        weeks = metric.estimated_consumption_weeks
        months = weeks * 12 / 52
        continue_consumption = weeks < context.policy.threshold_months * 52 / 12
        if continue_consumption:
            action = A.CONTINUE_CONSUMPTION
            gap("DECISION_SPEC_GAP", "CONSUMPTION_OWNER", rule.source, blocking=False)
        else:
            action, owner = A.NEGOTIATE_SUPPLIER_ORDER_REDUCTION, O.SUPPLIER
    elif rule.action_code is None:
        checks.append(RequiredCheck(code="AFTER_SALES_SPEC_AVAILABLE", passed=False))
        gap("DECISION_SPEC_GAP", "DC-16", rule.source)
        return finish(S.NOT_EVALUABLE)
    elif gaps:
        return finish(S.NOT_EVALUABLE)
    else:
        action = rule.action_code
        if owner == O.MPM:
            contact = bundle.inputs.supply.mpm
    return finish(S.DECIDED)
