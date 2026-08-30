"""Audited business rule catalog. Synthetic generator thresholds are not imported."""
from dataclasses import dataclass
from decimal import localcontext

from app.system_b.diagnosis.business_models import BusinessRuleEvaluation, DiagnosisCode, RuleGap
from app.system_b.diagnosis.models import EvidenceBundle, EvidenceKind as K, MissingCode, MissingEvidence, RuleState as S
from app.system_b.diagnosis.parameters import BusinessDiagnosisPolicy
from app.system_b.analytics.calculations import DECIMAL_CONTEXT


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
    def evaluate(self, bundle: EvidenceBundle, policy: BusinessDiagnosisPolicy | None = None,
                 preceding: tuple[BusinessRuleEvaluation, ...] = ()) -> BusinessRuleEvaluation:
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
        return self._nontrial(bundle, policy, preceding)

    def _nontrial(self, bundle, policy, preceding):
        used = [AGE_FACT, ORG_FACT]
        parameter_fields = []

        def result(state, code, *, missing=(), gaps=()):
            return BusinessRuleEvaluation(rule_id=self.rule_id, rule_version=self.version, diagnosis_code=self.diagnosis_code,
                priority=self.priority, state=state, reason_summary_code=code, used_evidence_ids=tuple(dict.fromkeys(used)),
                used_policy_fields=tuple(dict.fromkeys(parameter_fields)), missing_evidence=missing, rule_gaps=gaps)

        def absent_parameter(name):
            return result(S.NOT_EVALUABLE, "MISSING_POLICY_PARAMETER", gaps=(RuleGap(gap_id=name,
                code="MISSING_POLICY_PARAMETER", source="BusinessDiagnosisPolicy: explicit caller input required"),))

        def absent(kind, code):
            return result(S.NOT_EVALUABLE, code, missing=(MissingEvidence(kind=kind, code=MissingCode.MISSING_REQUIRED_FIELD,
                                                                        analytics_reason_codes=(code,)),))

        # Internal fallback has no independent positive predicate: every higher
        # applicable rule must have evaluated to false, never merely be missing.
        if self.rule_id == "business_internal_obsolescence":
            higher = [item for item in preceding if item.priority < self.priority]
            if {item.rule_id for item in higher} != {rule.rule_id for rule in BUSINESS_RULES if rule.priority < self.priority}:
                return absent(K.PO, "INCOMPLETE_PRECEDING_EVALUATIONS")
            for item in higher:
                used.extend(item.used_evidence_ids)
                parameter_fields.extend(item.used_policy_fields)
            if any(item.state == S.MATCHED for item in higher):
                return result(S.NOT_MATCHED, "EXCLUDED_BY_HIGHER_PRIORITY_MATCH")
            if any(item.state == S.NOT_EVALUABLE for item in higher):
                return result(S.NOT_EVALUABLE, "HIGHER_PRIORITY_NOT_EVALUABLE",
                    missing=tuple(dict.fromkeys(m for item in higher for m in item.missing_evidence)),
                    gaps=tuple(dict.fromkeys(g for item in higher for g in item.rule_gaps)))
            return result(S.MATCHED, "ALL_HIGHER_PRIORITY_RULES_EXCLUDED")

        if policy is None or policy.demand_change is None:
            return absent_parameter("demand_change")
        missing = bundle.missing_for((K.PROJECT_SELECTION, K.ALIGNED_FORECAST))
        if missing:
            return result(S.NOT_EVALUABLE, "MISSING_COMPARABLE_PROJECT_EVIDENCE", missing=missing)
        exposure = bundle.analytics.project_exposure
        project_id = exposure.top_contributing_project
        parameters = policy.demand_change
        parameter_fields.extend(("demand_change.total_drop_ratio", "demand_change.later_shift_ratio",
                                 "demand_change.min_comparison_months", "demand_change.post_version_count"))
        comparisons = bundle.analytics.anchor_comparisons.comparisons[:parameters.post_version_count]
        if len(comparisons) != parameters.post_version_count or any(len(item.periods) < parameters.min_comparison_months for item in comparisons):
            return absent(K.ALIGNED_FORECAST, "INSUFFICIENT_POLICY_COMPARISON_WINDOW")
        used.extend(bundle.fact_ids(K.PROJECT_SELECTION))
        for item in comparisons:
            used.extend(fact.evidence_id for fact in bundle.facts if fact.kind == K.ALIGNED_FORECAST
                        and fact.evidence_id.startswith(f"aligned.{item.post_position}."))
        with localcontext(DECIMAL_CONTEXT):
            significant = any((item.total_change_rate is not None and item.total_change_rate <= -parameters.total_drop_ratio)
                              or (item.later_shift_share is not None and item.later_shift_share >= parameters.later_shift_ratio)
                              for item in comparisons)
        change_rule = self.rule_id in ("business_customer_obsolescence", "business_demand_adjustment")
        if change_rule and not significant:
            return result(S.NOT_MATCHED, "NO_SIGNIFICANT_CHANGE_IN_POLICY_WINDOW")
        if not change_rule and significant:
            return result(S.NOT_MATCHED, "EXCLUDED_BY_SIGNIFICANT_CHANGE")

        if self.rule_id == "business_stockpile":
            after = next((item for item in preceding if item.rule_id == "business_after_sales"), None)
            if after is None:
                return absent(K.CURRENT_LIFECYCLE, "MISSING_AFTER_SALES_EVALUATION")
            used.extend(after.used_evidence_ids)
            parameter_fields.extend(after.used_policy_fields)
            if after.state == S.MATCHED:
                return result(S.NOT_MATCHED, "EXCLUDED_BY_AFTER_SALES")
            if after.state == S.NOT_EVALUABLE:
                return result(S.NOT_EVALUABLE, "AFTER_SALES_NOT_EVALUABLE", missing=after.missing_evidence, gaps=after.rule_gaps)
            if policy.valid_stockpile_tags is None:
                return absent_parameter("valid_stockpile_tags")
            missing = bundle.missing_for((K.STOCKPILE_HISTORY,))
            if missing:
                return result(S.NOT_EVALUABLE, "MISSING_HISTORICAL_STOCKPILE", missing=missing)
            parameter_fields.append("valid_stockpile_tags")
            used.extend(bundle.fact_ids(K.STOCKPILE_HISTORY))
            valid = any(row.stockpile_tag in policy.valid_stockpile_tags for row in bundle.inputs.stockpile.page.items)
            return result(S.MATCHED if valid else S.NOT_MATCHED, "VALID_HISTORICAL_STOCKPILE" if valid else "NO_VALID_HISTORICAL_STOCKPILE")

        products = [row for row in bundle.inputs.products if row.project_id == project_id]
        if not products or any(row.product_config_id is None for row in products):
            return absent(K.CURRENT_LIFECYCLE, "MISSING_SELECTED_PROJECT_LIFECYCLE")
        stages = {row.lifecycle_stage for row in products}
        if len(stages) != 1:
            return absent(K.CURRENT_LIFECYCLE, "CONFLICTING_CURRENT_LIFECYCLE")
        used.extend(fact.evidence_id for fact in bundle.facts if fact.kind == K.CURRENT_LIFECYCLE
                    and any(key.name == "project_id" and key.value == project_id for key in fact.entity_keys))
        eol = stages == {"EOL"}
        if change_rule:
            matched = eol if self.rule_id == "business_customer_obsolescence" else not eol
            return result(S.MATCHED if matched else S.NOT_MATCHED,
                          "SIGNIFICANT_CHANGE_LIFECYCLE_MATCH" if matched else "EXCLUDED_BY_CURRENT_LIFECYCLE")
        if not eol:
            return result(S.NOT_MATCHED, "CURRENT_PROJECT_NOT_EOL")
        if policy.after_sales is None:
            return absent_parameter("after_sales")
        parameters = policy.after_sales
        parameter_fields.extend(("after_sales.max_average_weekly_qty", "after_sales.min_nonzero_weeks", "after_sales.min_consecutive_weeks"))
        project = next(row for row in exposure.rankings if row.project_id == project_id)
        matched = (0 < project.average_weekly_qty <= parameters.max_average_weekly_qty
                   and project.nonzero_week_count >= parameters.min_nonzero_weeks
                   and project.longest_nonzero_run >= parameters.min_consecutive_weeks)
        return result(S.MATCHED if matched else S.NOT_MATCHED, "CURRENT_EOL_CONTINUOUS_LOW_DEMAND" if matched else "AFTER_SALES_PATTERN_NOT_MET")


# Explicit policy ranks from SCENARIO_RULES §2, not module/enum discovery order.
BUSINESS_RULES = (
    BusinessRule("business_trial", "1.0.0", "TRIAL_INVENTORY_ORGANIZATION", DiagnosisCode.TRIAL,
                 10, (K.PO, K.PO_AGING)),
    BusinessRule("business_customer_obsolescence", "2.0.0", "CHANGED_DEMAND_CURRENT_EOL",
                 DiagnosisCode.PROJECT_OBSOLESCENCE, 20, (K.PO, K.PO_AGING, K.PROJECT_SELECTION, K.ALIGNED_FORECAST, K.CURRENT_LIFECYCLE)),
    BusinessRule("business_demand_adjustment", "2.0.0", "CHANGED_DEMAND_CURRENT_NON_EOL",
                 DiagnosisCode.DEMAND_ADJUSTMENT, 20, (K.PO, K.PO_AGING, K.PROJECT_SELECTION, K.ALIGNED_FORECAST, K.CURRENT_LIFECYCLE)),
    BusinessRule("business_after_sales", "2.0.0", "UNCHANGED_DEMAND_CURRENT_EOL_CONTINUITY",
                 DiagnosisCode.AFTER_SALES, 30, (K.PO, K.PO_AGING, K.PROJECT_SELECTION, K.ALIGNED_FORECAST, K.CURRENT_LIFECYCLE)),
    BusinessRule("business_stockpile", "2.0.0", "HISTORICAL_VALID_STOCKPILE_AFTER_EXCLUSIONS",
                 DiagnosisCode.STOCKPILE, 40, (K.PO, K.PO_AGING, K.PROJECT_SELECTION, K.ALIGNED_FORECAST, K.CURRENT_LIFECYCLE, K.STOCKPILE_HISTORY)),
    BusinessRule("business_internal_obsolescence", "2.0.0", "INTERNAL_OBSOLESCENCE_AFTER_EXCLUSIONS",
                 DiagnosisCode.PROJECT_OBSOLESCENCE, 50,
                 (K.PO, K.PO_AGING, K.PROJECT_SELECTION, K.ALIGNED_FORECAST, K.CURRENT_LIFECYCLE, K.STOCKPILE_HISTORY),
                 ),
)
