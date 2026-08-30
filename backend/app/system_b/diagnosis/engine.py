"""Ordered, deterministic evaluation and evidence closure; no I/O or wall clock."""
from app.system_b.diagnosis.assembler import assemble_evidence, entity_keys, EvidenceAssemblyError
from app.system_b.diagnosis.models import (
    Completeness, DiagnosisResult, DiagnosisStatus, EvidenceBundle, RuleEvaluation, RuleState,
)
from app.system_b.diagnosis.rules import DiagnosisRule, FOUNDATION_RULES, OVERDUE_THRESHOLD_RULE


def evaluate_rule(rule: DiagnosisRule, bundle: EvidenceBundle) -> RuleEvaluation:
    """Requirements are enforced centrally, including for a future custom rule."""
    missing = bundle.missing_for(rule.required_evidence)
    if missing:
        return RuleEvaluation(rule_id=rule.rule_id, rule_version=rule.version,
                              state=RuleState.NOT_EVALUABLE, missing_evidence=missing)
    result = rule.evaluate(bundle)
    if (result.rule_id != rule.rule_id or result.rule_version != rule.version
            or result.missing_evidence or result.state == RuleState.NOT_EVALUABLE
            or ((result.state == RuleState.MATCHED) != (result.signal is not None))):
        raise ValueError("INVALID_RULE_RESULT")
    allowed = {fact.evidence_id for fact in bundle.facts if fact.kind in rule.required_evidence}
    if not result.used_evidence_ids or not set(result.used_evidence_ids) <= allowed:
        raise ValueError("INVALID_RULE_EVIDENCE_REFERENCE")
    return result


def diagnose(bundle: EvidenceBundle, *, rules: tuple[DiagnosisRule, ...] = FOUNDATION_RULES) -> DiagnosisResult:
    # Prevent a caller from attaching stale/foreign metrics or forging trace links.
    if assemble_evidence(bundle.inputs) != bundle:
        raise EvidenceAssemblyError("BUNDLE_DERIVATION_MISMATCH")
    ids = [rule.rule_id for rule in rules]
    if not rules or len(ids) != len(set(ids)) or any(not rule.rule_id or not rule.version or not rule.required_evidence for rule in rules):
        raise ValueError("INVALID_RULE_REGISTRY")
    evaluations = tuple(evaluate_rule(rule, bundle) for rule in rules)
    required = tuple(dict.fromkeys(kind for rule in rules for kind in rule.required_evidence))
    missing = bundle.missing_for(required)
    status = DiagnosisStatus.INSUFFICIENT_EVIDENCE if missing else DiagnosisStatus.FOUNDATION_ONLY
    eligibility = next((item for item in evaluations if item.rule_id == OVERDUE_THRESHOLD_RULE.rule_id), None)
    if eligibility is not None and eligibility.state == RuleState.NOT_MATCHED:
        status = DiagnosisStatus.NOT_ELIGIBLE
    selected = set()
    by_id = {fact.evidence_id: fact for fact in bundle.facts}

    def include(address):
        if address not in selected:
            selected.add(address)
            for parent in by_id[address].derived_from:
                include(parent)

    for evaluation in evaluations:
        for address in evaluation.used_evidence_ids:
            include(address)
    return DiagnosisResult(
        dataset_version_id=bundle.inputs.po.dataset_version_id, as_of_date=bundle.inputs.po.snapshot_date,
        entity_keys=entity_keys(bundle.inputs.po), status=status,
        completeness=Completeness.PARTIAL if missing else Completeness.COMPLETE,
        completeness_scope=tuple(ids), signals=tuple(item.signal for item in evaluations if item.signal is not None),
        evaluations=evaluations, missing_evidence=missing,
        evidence_trace=tuple(fact for fact in bundle.facts if fact.evidence_id in selected),
    )
