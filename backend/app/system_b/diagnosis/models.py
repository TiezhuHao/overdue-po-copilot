"""Immutable evidence and evaluation contracts. Foundation signals are not causes."""
from enum import StrEnum
from typing import Literal
from uuid import UUID

from app.system_b.models import (
    CalendarDate, CanonicalModel, CanonicalPage, ForecastSnapshot, MaterialSupplyDemand,
    ProductConfig, PurchaseOrder, Quantity, StockpileRecord, WeeklyForecastSnapshot,
)
from app.system_b.analytics.models import (
    ConsumptionMetrics, CoverageMetrics, ForecastChangeMetrics, PoAgingMetrics, SupplyDemandMetrics,
)


class EvidenceKind(StrEnum):
    PO = "PO"
    PO_AGING = "PO_AGING"
    PO_CONSUMPTION = "PO_CONSUMPTION"
    INVENTORY_COVERAGE = "INVENTORY_COVERAGE"
    SUPPLY_DEMAND = "SUPPLY_DEMAND"
    FORECAST_PAIR = "FORECAST_PAIR"
    FORECAST_CHANGE = "FORECAST_CHANGE"
    WEEKLY_FORECAST = "WEEKLY_FORECAST"
    PROJECT_CONTRIBUTION = "PROJECT_CONTRIBUTION"
    CURRENT_LIFECYCLE = "CURRENT_LIFECYCLE"
    HISTORICAL_LIFECYCLE = "HISTORICAL_LIFECYCLE"
    STOCKPILE_HISTORY = "STOCKPILE_HISTORY"
    MPM = "MPM"


class MissingCode(StrEnum):
    NOT_PROVIDED = "NOT_PROVIDED"
    MISSING_STABLE_ID = "MISSING_STABLE_ID"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    INCOMPLETE_COLLECTION = "INCOMPLETE_COLLECTION"
    HISTORICAL_LIFECYCLE_UNAVAILABLE = "HISTORICAL_LIFECYCLE_UNAVAILABLE"


class MissingEvidence(CanonicalModel):
    kind: EvidenceKind
    code: MissingCode
    fields: tuple[str, ...] = ()
    analytics_reason_codes: tuple[str, ...] = ()


class EntityKey(CanonicalModel):
    name: str
    value: UUID


class EvidenceFact(CanonicalModel):
    # Local deterministic address, scoped by the result's PO/dataset identity.
    evidence_id: str
    kind: EvidenceKind
    source: Literal["R1", "R2", "R3", "R4", "R5", "R6", "ANALYTICS"]
    entity_keys: tuple[EntityKey, ...]
    dataset_version_id: UUID
    snapshot_date: CalendarDate
    observed_on: CalendarDate
    version_date: CalendarDate | None = None
    version_sequence: int | None = None
    period: CalendarDate | None = None
    field: str
    observed_value: Quantity | str | int | bool | CalendarDate | UUID | None
    derived_from: tuple[str, ...] = ()


class HistoricalStockpileQuery(CanonicalModel):
    """Caller retains exact request scope; a bare empty page cannot prove absence."""
    material_id: UUID
    as_of_date: CalendarDate
    page: CanonicalPage[StockpileRecord]
    # An explicit revision override cannot prove the default as-of selection.
    requested_version_id: UUID | None = None


class EvidenceInputs(CanonicalModel):
    po: PurchaseOrder
    weekly: WeeklyForecastSnapshot | None = None
    supply: MaterialSupplyDemand | None = None
    previous_forecast: ForecastSnapshot | None = None
    current_forecast: ForecastSnapshot | None = None
    products: tuple[ProductConfig, ...] = ()
    stockpile: HistoricalStockpileQuery | None = None


class AnalyticsEvidence(CanonicalModel):
    aging: PoAgingMetrics
    consumption: ConsumptionMetrics
    coverage: CoverageMetrics
    supply_demand: SupplyDemandMetrics
    forecast_change: ForecastChangeMetrics


class EvidenceBundle(CanonicalModel):
    inputs: EvidenceInputs
    analytics: AnalyticsEvidence
    facts: tuple[EvidenceFact, ...]
    missing_evidence: tuple[MissingEvidence, ...]

    def missing_for(self, kinds: tuple[EvidenceKind, ...]) -> tuple[MissingEvidence, ...]:
        return tuple(item for item in self.missing_evidence if item.kind in kinds)

    def fact_ids(self, kind: EvidenceKind) -> tuple[str, ...]:
        return tuple(fact.evidence_id for fact in self.facts if fact.kind == kind)


class RuleState(StrEnum):
    MATCHED = "MATCHED"
    NOT_MATCHED = "NOT_MATCHED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class SignalCode(StrEnum):
    OVERDUE_THRESHOLD_EXCEEDED = "OVERDUE_THRESHOLD_EXCEEDED"
    HISTORICAL_STOCKPILE_RECORD_PRESENT = "HISTORICAL_STOCKPILE_RECORD_PRESENT"
    NEGATIVE_FORECAST_CHANGE = "NEGATIVE_FORECAST_CHANGE"


class RuleEvaluation(CanonicalModel):
    rule_id: str
    rule_version: str
    state: RuleState
    signal: SignalCode | None = None
    used_evidence_ids: tuple[str, ...] = ()
    missing_evidence: tuple[MissingEvidence, ...] = ()


class DiagnosisStatus(StrEnum):
    FOUNDATION_ONLY = "FOUNDATION_ONLY"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Completeness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class DiagnosisResult(CanonicalModel):
    dataset_version_id: UUID
    as_of_date: CalendarDate
    entity_keys: tuple[EntityKey, ...]
    status: DiagnosisStatus
    # No final cause is established by the Phase 2A supporting rules.
    primary_reason: None = None
    completeness: Completeness
    completeness_scope: tuple[str, ...]
    signals: tuple[SignalCode, ...]
    evaluations: tuple[RuleEvaluation, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    evidence_trace: tuple[EvidenceFact, ...]
