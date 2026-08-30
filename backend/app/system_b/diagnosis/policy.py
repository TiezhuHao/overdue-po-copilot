"""Deterministic primary selection; unresolved exclusions never become false."""
from app.system_b.diagnosis.business_models import (
    BusinessDiagnosisResult, BusinessRuleEvaluation, BusinessStatus as B, SuppressedMatch,
)
from app.system_b.diagnosis.business_rules import BUSINESS_RULES
from app.system_b.diagnosis.engine import diagnose
from app.system_b.diagnosis.models import Completeness, DiagnosisStatus, EvidenceBundle, RuleState as S


POLICY_ID = "procurement_diagnosis"
POLICY_VERSION = "1.0.0"


def select_primary(evaluations: tuple[BusinessRuleEvaluation, ...]):
    """Select only among complete business matches; never consume supporting signals."""
    if not evaluations or len({item.rule_id for item in evaluations}) != len(evaluations):
        raise ValueError("INVALID_BUSINESS_EVALUATIONS")
    matches = [item for item in evaluations if item.state == S.MATCHED]
    unresolved = [item for item in evaluations if item.state == S.NOT_EVALUABLE]
    if not matches:
        return None, B.UNRESOLVED if unresolved else B.NO_MATCH, "MISSING_BUSINESS_EVIDENCE" if unresolved else "NO_BUSINESS_RULE_MATCH"
    best_priority = min(item.priority for item in matches)
    best = [item for item in matches if item.priority == best_priority]
    if len(best) != 1:
        return None, B.UNRESOLVED, "CONFLICTING_RULE_MATCHES"
    if any(item.priority <= best_priority for item in unresolved):
        return None, B.UNRESOLVED, "HIGHER_OR_EQUAL_PRIORITY_UNRESOLVED"
    return best[0], B.DIAGNOSED, "PRIMARY_RULE_MATCHED"


def diagnose_business(bundle: EvidenceBundle) -> BusinessDiagnosisResult:
    # Foundation validates the full bundle's derivation before any business rule.
    foundation = diagnose(bundle)
    evaluations = tuple(rule.evaluate(bundle) for rule in BUSINESS_RULES)
    primary, status, summary = select_primary(evaluations)
    if foundation.status == DiagnosisStatus.NOT_ELIGIBLE:
        primary, status, summary = None, B.NOT_ELIGIBLE, "PO_NOT_ELIGIBLE"

    missing = tuple(dict.fromkeys(item for result in evaluations for item in result.missing_evidence))
    gaps = tuple(dict.fromkeys(gap for result in evaluations for gap in result.rule_gaps))
    used = {fact.evidence_id for fact in foundation.evidence_trace}
    facts = {fact.evidence_id: fact for fact in bundle.facts}

    def include(address):
        if address not in used:
            used.add(address)
            for parent in facts[address].derived_from:
                include(parent)

    for evaluation in evaluations:
        for address in evaluation.used_evidence_ids:
            include(address)
    suppressed = tuple(SuppressedMatch(rule_id=item.rule_id, rule_version=item.rule_version,
                                      suppressed_by_rule_id=primary.rule_id)
                       for item in evaluations if primary is not None and item.state == S.MATCHED
                       and item.priority > primary.priority)
    # Foundation evaluations retain their own missing evidence; business completeness
    # covers the explicit policy only. Optional signals cannot veto a complete TRIAL.
    values = foundation.model_dump(exclude={"status", "primary_reason", "completeness", "completeness_scope",
                                           "missing_evidence", "evidence_trace"})
    return BusinessDiagnosisResult(
        **values, status=status, primary_reason=primary.diagnosis_code if primary else None,
        primary_rule_id=primary.rule_id if primary else None, primary_rule_version=primary.rule_version if primary else None,
        policy_id=POLICY_ID, policy_version=POLICY_VERSION, reason_summary_code=summary,
        business_evaluations=evaluations, rule_gaps=gaps, suppressed_matches=suppressed,
        completeness=Completeness.PARTIAL if missing or gaps or status == B.UNRESOLVED else Completeness.COMPLETE,
        completeness_scope=tuple(rule.rule_id for rule in BUSINESS_RULES), missing_evidence=missing,
        evidence_trace=tuple(fact for fact in bundle.facts if fact.evidence_id in used),
    )
