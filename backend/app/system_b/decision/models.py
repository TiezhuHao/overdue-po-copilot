"""Immutable decision contracts; owner roles are not execution authorization."""
from enum import StrEnum
from typing import Literal, Self
from decimal import Decimal

from pydantic import model_validator

from app.system_b.models import CanonicalModel, MaterialMpmContact, Quantity
from app.system_b.diagnosis.business_models import BusinessDiagnosisResult
from app.system_b.diagnosis.models import EvidenceBundle, EvidenceFact


class DecisionStatus(StrEnum):
    DECIDED = "DECIDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ActionCode(StrEnum):
    REQUEST_MPM_CONFIRMATION = "REQUEST_MPM_CONFIRMATION"
    CONTINUE_CONSUMPTION = "CONTINUE_CONSUMPTION"
    NEGOTIATE_SUPPLIER_ORDER_REDUCTION = "NEGOTIATE_SUPPLIER_ORDER_REDUCTION"
    COMMUNICATE_CUSTOMER_OBSOLESCENCE = "COMMUNICATE_CUSTOMER_OBSOLESCENCE"
    COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE = "COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE"


class OwnerRole(StrEnum):
    MPM = "MPM"
    SUPPLIER = "SUPPLIER"
    CUSTOMER = "CUSTOMER"
    BUSINESS_UNIT = "BUSINESS_UNIT"


class BusinessDecisionPolicy(CanonicalModel):
    policy_id: Literal["confirmed_consumption"] = "confirmed_consumption"
    version: Literal["1.0.0"] = "1.0.0"
    threshold_months: Quantity | None = None
    source: Literal["AT-037; SCENARIO_RULES §7/§12"] = "AT-037; SCENARIO_RULES §7/§12"

    @model_validator(mode="after")
    def confirmed_threshold(self) -> Self:
        if self.threshold_months is not None and self.threshold_months != Decimal(6):
            raise ValueError("UNCONFIRMED_CONSUMPTION_THRESHOLD")
        return self


CONFIRMED_CONSUMPTION_POLICY = BusinessDecisionPolicy(threshold_months=Decimal(6))


class DecisionContext(CanonicalModel):
    diagnosis: BusinessDiagnosisResult
    evidence: EvidenceBundle
    policy: BusinessDecisionPolicy | None = None


class RequiredCheck(CanonicalModel):
    code: Literal["SOURCE_DIAGNOSIS_VALID", "MATERIAL_MPM_AVAILABLE", "CONSUMPTION_AVAILABLE",
                  "CONSUMPTION_POLICY_AVAILABLE", "AFTER_SALES_SPEC_AVAILABLE"]
    passed: bool
    evidence_refs: tuple[str, ...] = ()


class UnresolvedRequirement(CanonicalModel):
    code: Literal["DIAGNOSIS_UNRESOLVED", "UNSUPPORTED_DIAGNOSIS_RULE", "MISSING_REQUIRED_EVIDENCE",
                  "MISSING_POLICY_PARAMETER", "DECISION_SPEC_GAP"]
    requirement: str
    blocking: bool = True
    source: str


class DecisionAction(CanonicalModel):
    action_code: ActionCode
    owner_role: OwnerRole | None
    priority: int
    required: Literal[True] = True
    evidence_refs: tuple[str, ...]
    decision_rule_id: str
    decision_rule_version: str
    mpm_contact: MaterialMpmContact | None = None


class DecisionResult(CanonicalModel):
    decision_status: DecisionStatus
    decision_rule_id: str | None = None
    decision_rule_version: str | None = None
    source_diagnosis: BusinessDiagnosisResult
    decision_policy: BusinessDecisionPolicy | None = None
    policy_fingerprint: str | None = None
    used_policy_fields: tuple[str, ...] = ()
    owner_role: OwnerRole | None = None
    actions: tuple[DecisionAction, ...] = ()
    required_checks: tuple[RequiredCheck, ...]
    unresolved_requirements: tuple[UnresolvedRequirement, ...] = ()
    evidence_trace: tuple[EvidenceFact, ...]
    estimated_consumption_months: Quantity | None = None

    @model_validator(mode="after")
    def consistent_actions(self) -> Self:
        decided = self.decision_status == DecisionStatus.DECIDED
        if decided != bool(self.actions):
            raise ValueError("DECISION_ACTION_STATUS_MISMATCH")
        if decided and (any(item.blocking for item in self.unresolved_requirements)
                        or any(not item.passed for item in self.required_checks)):
            raise ValueError("ACTION_WITH_UNRESOLVED_REQUIREMENT")
        refs = {fact.evidence_id for fact in self.evidence_trace}
        for action in self.actions:
            if (not action.evidence_refs or not set(action.evidence_refs) <= refs
                    or action.decision_rule_id != self.decision_rule_id
                    or action.decision_rule_version != self.decision_rule_version
                    or action.owner_role != self.owner_role):
                raise ValueError("INVALID_ACTION_PROVENANCE")
        return self
