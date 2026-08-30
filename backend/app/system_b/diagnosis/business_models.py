"""Business results are distinct from Phase 2A supporting-signal results."""
from enum import StrEnum
from typing import Literal, Self

from pydantic import model_validator

from app.system_b.models import CanonicalModel
from app.system_b.diagnosis.models import DiagnosisResult, MissingEvidence, RuleState
from app.system_b.diagnosis.parameters import BusinessDiagnosisPolicy


class DiagnosisCode(StrEnum):
    TRIAL = "TRIAL"
    STOCKPILE = "STOCKPILE"
    DEMAND_ADJUSTMENT = "DEMAND_ADJUSTMENT"
    AFTER_SALES = "AFTER_SALES"
    PROJECT_OBSOLESCENCE = "PROJECT_OBSOLESCENCE"


class BusinessStatus(StrEnum):
    DIAGNOSED = "DIAGNOSED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNRESOLVED = "UNRESOLVED"
    NO_MATCH = "NO_MATCH"


class RuleGap(CanonicalModel):
    gap_id: str
    code: Literal["RULE_SPEC_GAP", "CONTRACT_GAP", "MISSING_POLICY_PARAMETER"]
    source: str


class BusinessRuleEvaluation(CanonicalModel):
    rule_id: str
    rule_version: str
    diagnosis_code: DiagnosisCode
    priority: int
    state: RuleState
    reason_summary_code: str
    used_evidence_ids: tuple[str, ...] = ()
    missing_evidence: tuple[MissingEvidence, ...] = ()
    rule_gaps: tuple[RuleGap, ...] = ()
    used_policy_fields: tuple[str, ...] = ()


class SuppressedMatch(CanonicalModel):
    rule_id: str
    rule_version: str
    suppressed_by_rule_id: str
    reason_summary_code: Literal["SUPPRESSED_BY_HIGHER_PRIORITY_RULE"] = "SUPPRESSED_BY_HIGHER_PRIORITY_RULE"


class BusinessDiagnosisResult(DiagnosisResult):
    status: BusinessStatus
    primary_reason: DiagnosisCode | None = None
    primary_rule_id: str | None = None
    primary_rule_version: str | None = None
    policy_id: str
    policy_version: str
    business_policy: BusinessDiagnosisPolicy | None = None
    policy_fingerprint: str | None = None
    routing_policy_version: str = "2.0.0"
    reason_summary_code: str
    business_evaluations: tuple[BusinessRuleEvaluation, ...]
    rule_gaps: tuple[RuleGap, ...] = ()
    suppressed_matches: tuple[SuppressedMatch, ...] = ()

    @model_validator(mode="after")
    def consistent_primary(self) -> Self:
        primary = (self.primary_reason, self.primary_rule_id, self.primary_rule_version)
        if self.status == BusinessStatus.DIAGNOSED:
            if any(value is None for value in primary):
                raise ValueError("INCOMPLETE_PRIMARY_DIAGNOSIS")
            matches = [item for item in self.business_evaluations
                       if item.rule_id == self.primary_rule_id and item.rule_version == self.primary_rule_version
                       and item.diagnosis_code == self.primary_reason and item.state == RuleState.MATCHED]
            if len(matches) != 1:
                raise ValueError("PRIMARY_RULE_NOT_MATCHED")
        elif any(value is not None for value in primary):
            raise ValueError("PRIMARY_WITHOUT_DIAGNOSIS")
        return self
