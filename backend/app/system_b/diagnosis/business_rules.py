"""Audited business rule catalog. Synthetic generator thresholds are not imported."""
from dataclasses import dataclass

from app.system_b.diagnosis.business_models import BusinessRuleEvaluation, DiagnosisCode, RuleGap
from app.system_b.diagnosis.models import EvidenceBundle, EvidenceKind as K, MissingCode, MissingEvidence, RuleState as S


CHANGE_GAP = RuleGap(gap_id="SIGNIFICANT_FORECAST_CHANGE", code="RULE_SPEC_GAP",
                     source="docs/SCENARIO_RULES.md#5; DC-15: synthetic-only thresholds")
PROJECT_GAP = RuleGap(gap_id="MOST_LIKELY_PROJECT_SELECTION", code="RULE_SPEC_GAP",
                      source="docs/SCENARIO_RULES.md#2; project selection not specified")
WINDOW_GAP = RuleGap(gap_id="ANCHOR_COMPARISON_WINDOW", code="CONTRACT_GAP",
                     source="docs/evidence-contracts.md; bundle contains only a same-month pair")
AFTER_SALES_GAP = RuleGap(gap_id="AFTER_SALES_PATTERN", code="RULE_SPEC_GAP",
                          source="docs/SCENARIO_RULES.md#11; synthetic-only continuity/level parameters")
STOCKPILE_GAP = RuleGap(gap_id="VALID_STOCKPILE_CONDITION", code="RULE_SPEC_GAP",
                        source="docs/SCENARIO_RULES.md#12; valid record/tag conditions not specified")
COMMON_GAPS = (CHANGE_GAP, PROJECT_GAP, WINDOW_GAP)
ORG_FACT = "po.inventory_organization_type"
AGE_FACT = "aging.threshold_delta_days"


@dataclass(frozen=True)
class BusinessRule:
    rule_id: str
    version: str
    semantic_label: str
    diagnosis_code: DiagnosisCode
    priority: int
    required_evidence: tuple[K, ...]
    rule_gaps: tuple[RuleGap, ...] = ()

    def evaluate(self, bundle: EvidenceBundle) -> BusinessRuleEvaluation:
        def result(state, code, *, used=(), missing=(), gaps=()):
            return BusinessRuleEvaluation(
                rule_id=self.rule_id, rule_version=self.version, diagnosis_code=self.diagnosis_code,
                priority=self.priority, state=state, reason_summary_code=code,
                used_evidence_ids=used, missing_evidence=missing, rule_gaps=gaps,
            )

        # Shared eligibility precedes any business predicate or exclusion.
        missing = bundle.missing_for((K.PO, K.PO_AGING))
        if missing:
            return result(S.NOT_EVALUABLE, "MISSING_ELIGIBILITY_EVIDENCE", missing=missing)
        if bundle.analytics.aging.threshold_delta_days <= 0:
            return result(S.NOT_MATCHED, "PO_NOT_ELIGIBLE", used=(AGE_FACT,))
        organization = bundle.inputs.po.inventory_organization_type
        used = (AGE_FACT, ORG_FACT)
        if organization not in ("TRIAL", "MASS_PRODUCTION"):
            return result(S.NOT_EVALUABLE, "UNSUPPORTED_ORGANIZATION_TYPE", used=used,
                          missing=(MissingEvidence(kind=K.PO, code=MissingCode.MISSING_REQUIRED_FIELD,
                                                   fields=("inventory_organization_type",)),))
        if self.rule_id == "business_trial":
            return result(S.MATCHED if organization == "TRIAL" else S.NOT_MATCHED,
                          "TRIAL_ORGANIZATION" if organization == "TRIAL" else "NON_TRIAL_ORGANIZATION", used=used)
        if organization == "TRIAL":
            # A known exclusion does not need evidence for the excluded branch.
            return result(S.NOT_MATCHED, "EXCLUDED_BY_TRIAL", used=used)
        return result(S.NOT_EVALUABLE, "BUSINESS_RULE_BLOCKED", used=used,
                      missing=bundle.missing_for(self.required_evidence), gaps=self.rule_gaps)


# Explicit policy ranks from SCENARIO_RULES §2, not module/enum discovery order.
BUSINESS_RULES = (
    BusinessRule("business_trial", "1.0.0", "TRIAL_INVENTORY_ORGANIZATION", DiagnosisCode.TRIAL,
                 10, (K.PO, K.PO_AGING)),
    BusinessRule("business_customer_obsolescence", "1.0.0", "CHANGED_DEMAND_CURRENT_EOL",
                 DiagnosisCode.PROJECT_OBSOLESCENCE, 20, (K.PO, K.PO_AGING, K.FORECAST_PAIR, K.CURRENT_LIFECYCLE), COMMON_GAPS),
    BusinessRule("business_demand_adjustment", "1.0.0", "CHANGED_DEMAND_CURRENT_NON_EOL",
                 DiagnosisCode.DEMAND_ADJUSTMENT, 20, (K.PO, K.PO_AGING, K.FORECAST_PAIR, K.CURRENT_LIFECYCLE), COMMON_GAPS),
    BusinessRule("business_after_sales", "1.0.0", "UNCHANGED_DEMAND_CURRENT_EOL_CONTINUITY",
                 DiagnosisCode.AFTER_SALES, 30, (K.PO, K.PO_AGING, K.FORECAST_PAIR, K.CURRENT_LIFECYCLE, K.WEEKLY_FORECAST),
                 (*COMMON_GAPS, AFTER_SALES_GAP)),
    BusinessRule("business_stockpile", "1.0.0", "HISTORICAL_VALID_STOCKPILE_AFTER_EXCLUSIONS",
                 DiagnosisCode.STOCKPILE, 40, (K.PO, K.PO_AGING, K.FORECAST_PAIR, K.CURRENT_LIFECYCLE, K.WEEKLY_FORECAST, K.STOCKPILE_HISTORY),
                 (*COMMON_GAPS, AFTER_SALES_GAP, STOCKPILE_GAP)),
    BusinessRule("business_internal_obsolescence", "1.0.0", "INTERNAL_OBSOLESCENCE_AFTER_EXCLUSIONS",
                 DiagnosisCode.PROJECT_OBSOLESCENCE, 50,
                 (K.PO, K.PO_AGING, K.FORECAST_PAIR, K.CURRENT_LIFECYCLE, K.WEEKLY_FORECAST, K.STOCKPILE_HISTORY),
                 (*COMMON_GAPS, AFTER_SALES_GAP, STOCKPILE_GAP)),
)
