"""Small public contracts; model-facing schemas never expose raw tool state."""
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from app.system_b.models import CanonicalModel, CalendarDate
from app.system_b.agent.models import ResolvedIdentity


class Intent(StrEnum):
    ANALYZE_OVERDUE_PO = "ANALYZE_OVERDUE_PO"
    GET_PO_ANALYTICS = "GET_PO_ANALYTICS"
    EXPLAIN_DIAGNOSIS = "EXPLAIN_DIAGNOSIS"
    GET_PROCUREMENT_DECISION = "GET_PROCUREMENT_DECISION"
    UNSUPPORTED = "UNSUPPORTED"


Identifier = Annotated[str, Field(min_length=1, max_length=120)]


class CopilotRequest(CanonicalModel):
    request_id: UUID = Field(default_factory=uuid4)
    user_query: Annotated[str, Field(min_length=1, max_length=2000)]
    dataset_version_id: UUID | None = None
    snapshot_date: CalendarDate | None = None
    po_line_schedule_id: UUID | None = None
    po_number: Identifier | None = None
    material_code: Identifier | None = None
    organization_id: UUID | None = None
    po_line_number: Annotated[int, Field(strict=True, gt=0)] | None = None
    shipment_number: Annotated[int, Field(strict=True, gt=0)] | None = None

    @field_validator("user_query", "po_number", "material_code")
    @classmethod
    def not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("text must not be blank")
        return value


class IntentDraft(CanonicalModel):
    intent: Intent
    po_number: str | None
    material_code: str | None


class Resolution(CanonicalModel):
    status: Literal["RESOLVED", "NOT_FOUND", "NEEDS_CLARIFICATION"]
    snapshot_date: CalendarDate | None = None
    po_line_schedule_id: UUID | None = None
    clarification_code: str | None = None
    candidate_schedule_ids: tuple[UUID, ...] = ()


class MetricValue(CanonicalModel):
    name: str
    value: str | None
    unit: str
    availability: str


class ProjectValue(CanonicalModel):
    project_id: UUID
    display_value: str | None


Section = Literal["结论", "为什么", "关键数据", "建议动作", "数据 / 规则限制"]


class EvidenceReference(CanonicalModel):
    reference_id: str
    source: str
    label: str
    snapshot_date: CalendarDate
    version_id: UUID | None = None
    version_date: CalendarDate | None = None
    rule_version: str | None = None


class GroundedFact(CanonicalModel):
    fact_id: str
    section: Section
    allowed_sentences: tuple[str, ...]
    evidence_reference_ids: tuple[str, ...]


class GroundingPacket(CanonicalModel):
    execution_status: str
    primary_reason: str | None
    owner_role: str | None
    action_codes: tuple[str, ...]
    metrics: tuple[MetricValue, ...]
    projects: tuple[ProjectValue, ...]
    facts: tuple[GroundedFact, ...]
    evidence_references: tuple[EvidenceReference, ...]


class DraftLine(CanonicalModel):
    fact_id: str
    text: str
    evidence_reference_ids: list[str]


class DraftSection(CanonicalModel):
    heading: Section
    lines: list[DraftLine]


class CopilotAnswerDraft(CanonicalModel):
    primary_reason: str | None
    owner_role: str | None
    action_codes: list[str]
    metrics: list[MetricValue]
    projects: list[ProjectValue]
    sections: list[DraftSection]


class PublicDiagnosis(CanonicalModel):
    status: str
    primary_reason: str | None
    primary_rule_id: str | None
    primary_rule_version: str | None
    supporting_signals: tuple[str, ...]


class PublicAction(CanonicalModel):
    action_code: str
    owner_role: str | None
    required: bool


class PublicDecision(CanonicalModel):
    status: str
    rule_id: str | None
    rule_version: str | None
    owner_role: str | None
    actions: tuple[PublicAction, ...]


class EvaluationHook(CanonicalModel):
    # The user query already lives in the request; never log it automatically.
    resolved_intent: Intent | None
    tool_path: tuple[str, ...] = ()
    business_status: str | None = None
    grounding_status: Literal["NOT_ATTEMPTED", "VALIDATED", "FALLBACK"] = "NOT_ATTEMPTED"


class CopilotResponse(CanonicalModel):
    request_id: UUID
    status: Literal["COMPLETED", "NOT_APPLICABLE", "UNRESOLVED", "FAILED", "NOT_FOUND", "NEEDS_CLARIFICATION"]
    answer: str
    answer_source: Literal["MODEL", "FALLBACK", "CLARIFICATION"]
    resolved_identity: ResolvedIdentity | None = None
    intent: Intent | None = None
    key_metrics: tuple[MetricValue, ...] = ()
    diagnosis: PublicDiagnosis | None = None
    decision: PublicDecision | None = None
    evidence_references: tuple[EvidenceReference, ...] = ()
    limitations: tuple[str, ...] = ()
    candidate_schedule_ids: tuple[UUID, ...] = ()
    execution_reference: UUID | None = None
    evaluation: EvaluationHook
