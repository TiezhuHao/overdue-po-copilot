"""Three supporting rules, with no final cause mapping or business tree."""
from dataclasses import dataclass
from typing import Callable, Protocol

from app.system_b.diagnosis.models import (
    EvidenceBundle, EvidenceKind as K, RuleEvaluation, RuleState as S, SignalCode,
)


class DiagnosisRule(Protocol):
    rule_id: str
    version: str
    semantic_label: str
    required_evidence: tuple[K, ...]

    def evaluate(self, bundle: EvidenceBundle) -> RuleEvaluation: ...


@dataclass(frozen=True)
class FoundationRule:
    rule_id: str
    version: str
    semantic_label: str
    required_evidence: tuple[K, ...]
    signal: SignalCode
    used_fields: tuple[str, ...]
    predicate: Callable[[EvidenceBundle], bool]

    def evaluate(self, bundle: EvidenceBundle) -> RuleEvaluation:
        missing = bundle.missing_for(self.required_evidence)
        used = tuple(fact.evidence_id for fact in bundle.facts
                     if fact.kind in self.required_evidence and fact.field in self.used_fields)
        if missing:
            return RuleEvaluation(rule_id=self.rule_id, rule_version=self.version, state=S.NOT_EVALUABLE,
                                  used_evidence_ids=used, missing_evidence=missing)
        matched = self.predicate(bundle)
        return RuleEvaluation(rule_id=self.rule_id, rule_version=self.version,
                              state=S.MATCHED if matched else S.NOT_MATCHED,
                              signal=self.signal if matched else None, used_evidence_ids=used)


OVERDUE_THRESHOLD_RULE = FoundationRule(
    "po_overdue_threshold", "1.0.0", "ELIGIBILITY", (K.PO_AGING,),
    SignalCode.OVERDUE_THRESHOLD_EXCEEDED, ("threshold_delta_days",),
    lambda bundle: bundle.analytics.aging.threshold_delta_days > 0,
)
STOCKPILE_PRESENCE_RULE = FoundationRule(
    "historical_stockpile_presence", "1.0.0", "EVIDENCE_PRESENCE", (K.STOCKPILE_HISTORY,),
    SignalCode.HISTORICAL_STOCKPILE_RECORD_PRESENT, ("record_count", "stockpile_tag"),
    lambda bundle: bool(bundle.inputs.stockpile.page.items),
)
FORECAST_REDUCTION_RULE = FoundationRule(
    "forecast_negative_change", "1.0.0", "DIRECTION_ONLY", (K.FORECAST_CHANGE,),
    SignalCode.NEGATIVE_FORECAST_CHANGE, ("forecast_change_qty",),
    lambda bundle: bundle.analytics.forecast_change.forecast_change_qty < 0,
)

# Execution order only, not the future business-cause priority tree.
FOUNDATION_RULES: tuple[DiagnosisRule, ...] = (
    OVERDUE_THRESHOLD_RULE, STOCKPILE_PRESENCE_RULE, FORECAST_REDUCTION_RULE,
)
