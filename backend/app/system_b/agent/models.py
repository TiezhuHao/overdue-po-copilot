"""Public version-one tool contracts and compact execution projections."""
from enum import StrEnum
from typing import Generic, Literal, TypeVar, Self
from uuid import UUID

from pydantic import model_validator

from app.system_b.models import CanonicalModel, CalendarDate, Quantity
from app.system_b.diagnosis.models import (
    AnalyticsEvidence, EvidenceFact, MissingEvidence, RuleEvaluation, SignalCode, Completeness,
)
from app.system_b.diagnosis.business_models import (
    BusinessStatus, DiagnosisCode, BusinessRuleEvaluation, RuleGap, SuppressedMatch,
)
from app.system_b.diagnosis.parameters import BusinessDiagnosisPolicy
from app.system_b.decision.models import (
    BusinessDecisionPolicy, DecisionStatus, DecisionAction, OwnerRole, RequiredCheck, UnresolvedRequirement,
)


class ToolName(StrEnum):
    CONTEXT = "get_overdue_po_context"
    ANALYTICS = "get_overdue_po_analytics"
    DIAGNOSIS = "diagnose_overdue_po"
    DECISION = "get_procurement_decision"


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_REJECTED = "UPSTREAM_REJECTED"
    UPSTREAM_INVALID_RESPONSE = "UPSTREAM_INVALID_RESPONSE"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    BUSINESS_UNRESOLVED = "BUSINESS_UNRESOLVED"
    INTERNAL_TOOL_FAILURE = "INTERNAL_TOOL_FAILURE"


class AgentIssue(CanonicalModel):
    code: ErrorCode
    tool: ToolName | None = None
    retryable: bool = False
    blocking: bool = True


class ContextRequest(CanonicalModel):
    request_id: UUID
    dataset_version_id: UUID
    snapshot_date: CalendarDate
    po_line_schedule_id: UUID


class AgentRequest(ContextRequest):
    operation: Literal["ANALYZE_OVERDUE_PO"] = "ANALYZE_OVERDUE_PO"
    diagnosis_policy: BusinessDiagnosisPolicy | None = None
    decision_policy: BusinessDecisionPolicy | None = None


class ResolvedIdentity(ContextRequest):
    po_header_id: UUID
    po_line_id: UUID
    material_id: UUID
    organization_id: UUID
    supplier_id: UUID


class ContextOutput(CanonicalModel):
    identity: ResolvedIdentity
    context_ref: str
    missing_sources: tuple[Literal["R2", "R3", "R4", "R5"], ...] = ()


class AnalyticsInput(CanonicalModel):
    identity: ResolvedIdentity
    context_ref: str


class DiagnosisInput(AnalyticsInput):
    policy: BusinessDiagnosisPolicy | None = None


class DecisionInput(AnalyticsInput):
    diagnosis_ref: str
    policy: BusinessDecisionPolicy | None = None


class AnalyticsOutput(CanonicalModel):
    identity: ResolvedIdentity
    context_ref: str
    metrics: AnalyticsEvidence
    missing_evidence: tuple[MissingEvidence, ...]


class DiagnosisOutput(CanonicalModel):
    identity: ResolvedIdentity
    context_ref: str
    trace_ref: str
    status: BusinessStatus
    primary_reason: DiagnosisCode | None
    primary_rule_id: str | None
    primary_rule_version: str | None
    reason_summary_code: str
    completeness: Completeness
    completeness_scope: tuple[str, ...]
    signals: tuple[SignalCode, ...]
    evaluations: tuple[RuleEvaluation, ...]
    business_evaluations: tuple[BusinessRuleEvaluation, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    rule_gaps: tuple[RuleGap, ...]
    suppressed_matches: tuple[SuppressedMatch, ...]
    policy_id: str
    policy_version: str
    business_policy: BusinessDiagnosisPolicy | None
    policy_fingerprint: str | None
    routing_policy_version: str


class DecisionOutput(CanonicalModel):
    identity: ResolvedIdentity
    context_ref: str
    source_diagnosis_ref: str
    trace_ref: str
    decision_status: DecisionStatus
    decision_rule_id: str | None
    decision_rule_version: str | None
    decision_policy: BusinessDecisionPolicy | None
    policy_fingerprint: str | None
    used_policy_fields: tuple[str, ...]
    owner_role: OwnerRole | None
    actions: tuple[DecisionAction, ...]
    required_checks: tuple[RequiredCheck, ...]
    unresolved_requirements: tuple[UnresolvedRequirement, ...]
    estimated_consumption_months: Quantity | None


T = TypeVar("T", bound=CanonicalModel)


class ToolResult(CanonicalModel, Generic[T]):
    status: Literal["SUCCESS", "ERROR"]
    output: T | None = None
    error: AgentIssue | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if ((self.status == "SUCCESS") != (self.output is not None)
                or (self.status == "ERROR") != (self.error is not None)):
            raise ValueError("INVALID_TOOL_ENVELOPE")
        return self


class ExecutionTrace(CanonicalModel):
    sequence: int
    node: str
    tool: ToolName | None = None
    input_identity: ResolvedIdentity | ContextRequest | None = None
    result_status: str
    selected_path: str
    downstream_trace_ref: str | None = None


class Provenance(CanonicalModel):
    context_ref: str | None = None
    diagnosis_ref: str | None = None
    decision_ref: str | None = None
    facts: tuple[EvidenceFact, ...] = ()


class AgentExecutionResult(CanonicalModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["COMPLETED", "NOT_APPLICABLE", "UNRESOLVED", "FAILED"]
    request: AgentRequest | None
    resolved_identity: ResolvedIdentity | None = None
    analytics: AnalyticsOutput | None = None
    diagnosis: DiagnosisOutput | None = None
    decision: DecisionOutput | None = None
    execution_trace: tuple[ExecutionTrace, ...]
    issues: tuple[AgentIssue, ...] = ()
    unresolved_requirements: tuple[UnresolvedRequirement, ...] = ()
    provenance: Provenance = Provenance()
