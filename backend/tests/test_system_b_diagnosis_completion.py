"""Explicit test-only policy parameters; no per-record answers in runtime inputs."""
from datetime import date
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.system_b.analytics.evidence_metrics import calculate_anchor_comparisons, calculate_project_exposure
from app.system_b.analytics.models import Availability as A
from app.system_b.diagnosis.assembler import assemble_evidence, EvidenceAssemblyError
from app.system_b.diagnosis.models import RuleState as S
from app.system_b.diagnosis.parameters import BusinessDiagnosisPolicy, DemandChangeParameters, AfterSalesParameters
from app.system_b.diagnosis.policy import diagnose_business
from app.system_b.models import ProjectWeekForecast
from tests.test_system_b_diagnosis import full_inputs, po, product, stockpile_query, PID, CONFIG
from tests.test_system_b_analytics import monthly, weeks


OTHER_PROJECT = UUID(int=900)


def policy(**updates):
    # Values explicitly chosen for tests; not a shipped demo or enterprise profile.
    values = dict(policy_id="test-only-policy", version="fixture-1",
                  demand_change=DemandChangeParameters(total_drop_ratio=Decimal("0.25"), later_shift_ratio=Decimal("0.25"),
                                                       min_comparison_months=6, post_version_count=2),
                  after_sales=AfterSalesParameters(max_average_weekly_qty=Decimal(3), min_nonzero_weeks=8, min_consecutive_weeks=4),
                  valid_stockpile_tags=("PLANNED",))
    return BusinessDiagnosisPolicy(**(values | updates))


def history(shape="stable", project_id=PID):
    result = []
    for position, version_date in enumerate((date(2025, 1, 27), date(2025, 2, 3), date(2025, 2, 10))):
        start = version_date.replace(day=1)
        for index in range(7):
            month = date(2025, start.month + index, 1)
            qty = Decimal(100)
            if position and shape == "reduction":
                qty = Decimal(50)
            if position and shape == "boundary":
                qty = Decimal(75)
            if position and shape == "shift" and month.month in (2, 3, 6, 7):
                qty = Decimal(0 if month.month in (2, 3) else 200)
            if shape == "zero":
                qty = Decimal(0)
            result.append(monthly(UUID(int=100 + position), version_date, str(qty), project_id=project_id,
                forecast_version_sequence=1, forecast_month=month, forecast_anchor_date=date(2025, 1, 31),
                window_position=position, window_role="BASELINE" if not position else "POST",
                horizon_start_month=start, horizon_end_month_exclusive=date(2025, start.month + 7, 1)))
    return tuple(result)


def facts(shape="stable", lifecycle="EOL", tag="PLANNED", first_qty="2", second_qty="1", **updates):
    inputs = full_inputs(po=po(po_reference_project_id=OTHER_PROJECT), products=(product(lifecycle_stage=lifecycle),),
                         stockpile=stockpile_query(stockpile_tag=tag), forecast_history=history(shape))
    first, second = weeks(first_qty, dated=True), weeks(second_qty, dated=True)
    rows = tuple(ProjectWeekForecast(**week.model_dump(), project_id=project_id)
                 for project_id, collection in ((PID, first), (OTHER_PROJECT, second)) for week in collection)
    total = weeks(str(Decimal(first_qty) + Decimal(second_qty)), dated=True)
    weekly = inputs.weekly.model_copy(update={"weeks": total, "project_contributions": rows})
    return inputs.model_copy(update={"weekly": weekly} | updates)


GOLDEN = [
    ("trial", {"po": po(inventory_organization_type="TRIAL")}, "TRIAL", "business_trial"),
    ("customer", {"shape": "reduction"}, "PROJECT_OBSOLESCENCE", "business_customer_obsolescence"),
    ("demand", {"shape": "reduction", "lifecycle": "NPI"}, "DEMAND_ADJUSTMENT", "business_demand_adjustment"),
    ("timing_shift", {"shape": "shift", "lifecycle": "MASS_PRODUCTION"}, "DEMAND_ADJUSTMENT", "business_demand_adjustment"),
    ("after_sales", {}, "AFTER_SALES", "business_after_sales"),
    ("stockpile", {"lifecycle": "MASS_PRODUCTION"}, "STOCKPILE", "business_stockpile"),
    ("internal", {"lifecycle": "MASS_PRODUCTION", "tag": "OTHER"}, "PROJECT_OBSOLESCENCE", "business_internal_obsolescence"),
    ("eol_stockpile", {"first_qty": "10"}, "STOCKPILE", "business_stockpile"),
    ("eol_internal", {"first_qty": "10", "tag": "OTHER"}, "PROJECT_OBSOLESCENCE", "business_internal_obsolescence"),
]


@pytest.mark.parametrize("name,values,reason,rule", GOLDEN, ids=[row[0] for row in GOLDEN])
def test_complete_golden_causes(name, values, reason, rule):
    result = diagnose_business(assemble_evidence(facts(**values)), policy())
    assert result.status == "DIAGNOSED" and result.primary_reason == reason and result.primary_rule_id == rule
    assert result.primary_rule_version == ("1.0.0" if rule == "business_trial" else "2.0.0")
    assert sum(item.state == S.MATCHED for item in result.business_evaluations) == 1
    assert result.business_policy == policy() and result.policy_id == "test-only-policy" and result.policy_version == "fixture-1"
    assert result.policy_fingerprint and result.routing_policy_version == "2.0.0"


def test_change_eol_and_after_sales_precede_stockpile():
    for shape, expected in (("reduction", "business_customer_obsolescence"), ("stable", "business_after_sales")):
        result = diagnose_business(assemble_evidence(facts(shape)), policy())
        assert result.primary_rule_id == expected
        stock = next(item for item in result.business_evaluations if item.rule_id == "business_stockpile")
        assert stock.state == S.NOT_MATCHED
        assert stock.reason_summary_code == ("EXCLUDED_BY_SIGNIFICANT_CHANGE" if shape == "reduction" else "EXCLUDED_BY_AFTER_SALES")


@pytest.mark.parametrize("missing", ["demand_change", "after_sales", "valid_stockpile_tags"])
def test_missing_policy_parameter_cannot_fall_back_to_internal(missing):
    # EOL high demand excludes after-sales only when its parameter is present.
    result = diagnose_business(assemble_evidence(facts(first_qty="10", tag="OTHER")), policy(**{missing: None}))
    assert result.status == "UNRESOLVED" and result.primary_reason is None
    internal = result.business_evaluations[-1]
    assert internal.state == S.NOT_EVALUABLE and any(gap.gap_id == missing for gap in result.rule_gaps)


def test_irrelevant_parameters_do_not_block_complete_higher_rule():
    bundle = assemble_evidence(facts("reduction", lifecycle="NPI"))
    assert diagnose_business(bundle, policy(after_sales=None, valid_stockpile_tags=None)).primary_reason == "DEMAND_ADJUSTMENT"


def test_different_explicit_policy_changes_result_and_trace():
    bundle = assemble_evidence(facts("reduction", lifecycle="NPI"))
    first = policy()
    second = policy(version="fixture-2", demand_change=first.demand_change.model_copy(update={"total_drop_ratio": Decimal("0.75")}))
    a, b = diagnose_business(bundle, first), diagnose_business(bundle, second)
    assert a.primary_reason == "DEMAND_ADJUSTMENT" and b.primary_reason == "STOCKPILE"
    assert a.policy_version != b.policy_version and a.policy_fingerprint != b.policy_fingerprint
    assert "demand_change.total_drop_ratio" in a.business_evaluations[1].used_policy_fields


@pytest.mark.parametrize("threshold,expected", [("0.2499", "DEMAND_ADJUSTMENT"), ("0.25", "DEMAND_ADJUSTMENT"), ("0.2501", "STOCKPILE")])
def test_significance_threshold_boundary(threshold, expected):
    supplied = policy()
    supplied = supplied.model_copy(update={"demand_change": supplied.demand_change.model_copy(update={"total_drop_ratio": Decimal(threshold)})})
    assert diagnose_business(assemble_evidence(facts("boundary", lifecycle="NPI")), supplied).primary_reason == expected


def test_tie_is_ambiguous_in_both_input_orders():
    inputs = facts(first_qty="2", second_qty="2")
    for rows in (inputs.weekly.project_contributions, tuple(reversed(inputs.weekly.project_contributions))):
        weekly = inputs.weekly.model_copy(update={"project_contributions": rows})
        metric = calculate_project_exposure(weekly)
        assert metric.top_contributing_project is None and metric.reason_codes == ("AMBIGUOUS_TOP_PROJECT",)
        assert metric.rankings[0].contribution_share == Decimal("0.5")
        result = diagnose_business(assemble_evidence(inputs.model_copy(update={"weekly": weekly})), policy())
        assert result.status == "UNRESOLVED" and result.business_evaluations[-1].state == S.NOT_EVALUABLE


@pytest.mark.parametrize("mode,code", [("missing", "MISSING_PROJECT_CONTRIBUTIONS"), ("partial", "INCOMPLETE_PROJECT_WINDOW"),
                                       ("mismatch", "PROJECT_CONTRIBUTION_TOTAL_MISMATCH"), ("zero", "NO_POSITIVE_PROJECT_DEMAND")])
def test_project_metric_does_not_infer_missing_zeros(mode, code):
    inputs = facts(first_qty="0", second_qty="0") if mode == "zero" else facts()
    updates = {}
    if mode == "missing": updates["project_contributions"] = None
    if mode == "partial": updates["project_contributions"] = inputs.weekly.project_contributions[1:]
    if mode == "mismatch": updates["weeks"] = weeks("999", dated=True)
    metric = calculate_project_exposure(inputs.weekly.model_copy(update=updates))
    assert metric.status == A.NOT_COMPUTABLE and code in metric.reason_codes


@pytest.mark.parametrize("mode", ["missing", "one_post", "missing_month", "wrong_anchor", "different_project", "same_date", "bad_horizon", "position_gap"])
def test_incomplete_or_incompatible_history_cannot_prove_no_change(mode):
    rows = history()
    if mode == "missing": rows = None
    if mode == "one_post": rows = rows[:14]
    if mode == "missing_month": rows = rows[1:]
    if mode == "different_project": rows = history(project_id=OTHER_PROJECT)
    if mode in ("wrong_anchor", "same_date", "bad_horizon", "position_gap"):
        changes = {"wrong_anchor": {"forecast_anchor_date": date(2025, 2, 1)},
                   "same_date": {"forecast_version_date": date(2025, 1, 31)},
                   "bad_horizon": {"horizon_end_month_exclusive": date(2025, 6, 1)},
                   "position_gap": {"window_position": 5}}[mode]
        rows = tuple(row.model_copy(update=changes) if row.window_position == 1 else row for row in rows)
    result = diagnose_business(assemble_evidence(facts(forecast_history=rows)), policy())
    assert result.status == "UNRESOLVED" and result.business_evaluations[-1].state == S.NOT_EVALUABLE


def test_month_alignment_and_forward_only_shift_math():
    metric = calculate_anchor_comparisons(po(), PID, history("shift"))
    assert metric.status == A.AVAILABLE
    for item in metric.comparisons:
        assert len(item.periods) == 6 and item.aligned_previous_total == item.aligned_current_total == Decimal(600)
        assert item.total_change_qty == 0 and item.total_change_rate == 0 and item.later_shift_qty == 200
        assert item.later_shift_share == Decimal("0.3333333333333333333333333333333333333333")
    rows = history("shift")
    reversed_shift = tuple(row.model_copy(update={"forecast_qty": Decimal(200 if row.forecast_month.month in (2, 3) else 0)})
                           if row.window_position and row.forecast_month.month in (2, 3, 6, 7) else row for row in rows)
    assert all(item.later_shift_qty == 0 for item in calculate_anchor_comparisons(po(), PID, reversed_shift).comparisons)


def test_zero_baseline_is_finite_and_can_prove_no_negative_change():
    result = calculate_anchor_comparisons(po(), PID, history("zero"))
    assert result.status == A.AVAILABLE
    assert all(item.total_change_rate is None and item.later_shift_share is None and item.later_shift_qty == 0 for item in result.comparisons)
    assert diagnose_business(assemble_evidence(facts("zero")), policy()).primary_reason == "AFTER_SALES"


@pytest.mark.parametrize("mode", ["missing_selected", "conflict"])
def test_lifecycle_must_belong_to_selected_project_and_be_consistent(mode):
    products = ((product(project_id=OTHER_PROJECT),) if mode == "missing_selected" else
                (product(), product(product_config_id=UUID(int=901), lifecycle_stage="NPI")))
    result = diagnose_business(assemble_evidence(facts("reduction", products=products)), policy())
    assert result.status == "UNRESOLVED" and result.primary_reason is None


def test_after_sales_requires_continuity_not_just_eol_or_total_quantity():
    inputs = facts(second_qty="0")
    source = inputs.weekly.project_contributions
    rows = tuple(row.model_copy(update={"forecast_qty": Decimal(26 if row.week_index == 1 and row.project_id == PID else 0)}) for row in source)
    buckets = tuple(row.model_copy(update={"forecast_qty": Decimal(26 if row.week_index == 1 else 0)}) for row in inputs.weekly.weeks)
    inputs = inputs.model_copy(update={"weekly": inputs.weekly.model_copy(update={"project_contributions": rows, "weeks": buckets})})
    result = diagnose_business(assemble_evidence(inputs), policy())
    assert result.primary_reason == "STOCKPILE"
    assert result.business_evaluations[3].reason_summary_code == "AFTER_SALES_PATTERN_NOT_MET"


def test_provenance_and_parameter_trace_follow_selected_project_not_reference():
    bundle = assemble_evidence(facts("reduction"))
    result = diagnose_business(bundle, policy())
    used = result.business_evaluations[1].used_evidence_ids
    assert "project_selection.top_contributing_project" in used
    trace = {fact.evidence_id: fact for fact in result.evidence_trace}
    assert trace["project_selection.top_contributing_project"].observed_value == PID
    aligned = trace["aligned.1.total_change_qty"]
    assert aligned.derived_from and all(parent in trace for parent in aligned.derived_from)
    source = [fact for fact in trace.values() if fact.source == "R3" and fact.evidence_id.startswith("history.")]
    assert source and all(fact.version_sequence == 1 and fact.version_date.year == 2025 for fact in source)
    assert all(any(key.name == "project_id" and key.value == PID for key in fact.entity_keys) for fact in source)


def test_policy_and_evidence_determinism_with_decimal_isolation():
    inputs, supplied = facts("shift"), policy()
    expected = diagnose_business(assemble_evidence(inputs), supplied).model_dump_json()
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        assert diagnose_business(assemble_evidence(inputs), supplied).model_dump_json() == expected


def test_shuffled_history_and_project_rows_produce_identical_result():
    inputs = facts("shift")
    shuffled = inputs.model_copy(update={"forecast_history": tuple(reversed(inputs.forecast_history)),
        "weekly": inputs.weekly.model_copy(update={"project_contributions": tuple(reversed(inputs.weekly.project_contributions))})})
    assert diagnose_business(assemble_evidence(inputs), policy()).model_dump_json() == diagnose_business(assemble_evidence(shuffled), policy()).model_dump_json()


@pytest.mark.parametrize("field,value", [("total_drop_ratio", "0"), ("total_drop_ratio", "1.1"), ("later_shift_ratio", "-0.1"),
                                         ("min_comparison_months", 8), ("post_version_count", 1)])
def test_invalid_demand_parameter_bounds(field, value):
    with pytest.raises(ValidationError):
        DemandChangeParameters.model_validate(policy().demand_change.model_dump() | {field: value})


def test_missing_required_post_prefix_and_minimum_month_count_are_traced():
    for fields in ({"post_version_count": 3}, {"min_comparison_months": 7}):
        supplied = policy()
        supplied = supplied.model_copy(update={"demand_change": supplied.demand_change.model_copy(update=fields)})
        result = diagnose_business(assemble_evidence(facts()), supplied)
        assert result.status == "UNRESOLVED"
        assert "demand_change.post_version_count" in result.business_evaluations[1].used_policy_fields


def test_complete_empty_historical_query_can_support_internal_after_exclusions():
    result = diagnose_business(assemble_evidence(facts(lifecycle="NPI", stockpile=stockpile_query(count=0))), policy())
    assert result.primary_rule_id == "business_internal_obsolescence"
    assert all(item.state == S.NOT_MATCHED for item in result.business_evaluations[:-1])


def test_missing_historical_query_blocks_fallback_even_when_after_sales_excluded():
    result = diagnose_business(assemble_evidence(facts(lifecycle="NPI", stockpile=None)), policy())
    assert result.status == "UNRESOLVED" and result.business_evaluations[-1].state == S.NOT_EVALUABLE


@pytest.mark.parametrize("limit,expected", [("1.999", "STOCKPILE"), ("2", "AFTER_SALES"), ("2.001", "AFTER_SALES")])
def test_after_sales_average_boundary_is_inclusive(limit, expected):
    supplied = policy()
    supplied = supplied.model_copy(update={"after_sales": supplied.after_sales.model_copy(update={"max_average_weekly_qty": Decimal(limit)})})
    assert diagnose_business(assemble_evidence(facts()), supplied).primary_reason == expected


@pytest.mark.parametrize("updates", [{"policy_id": " "}, {"valid_stockpile_tags": ()}, {"valid_stockpile_tags": ("PLANNED", "PLANNED")},
                                    {"expected_diagnosis": "TRIAL"}, {"responsible_project": str(PID)}])
def test_policy_rejects_invalid_parameters_and_answer_lookup_fields(updates):
    with pytest.raises(ValidationError):
        BusinessDiagnosisPolicy.model_validate(policy().model_dump() | updates)


def test_foreign_history_is_rejected_and_policy_construct_bypass_is_revalidated():
    rows = history()
    rows = (rows[0].model_copy(update={"dataset_version_id": UUID(int=999)}), *rows[1:])
    with pytest.raises(EvidenceAssemblyError, match="DATASET_MISMATCH"):
        assemble_evidence(facts(forecast_history=rows))
    supplied = policy()
    supplied = supplied.model_copy(update={"demand_change": supplied.demand_change.model_copy(update={"total_drop_ratio": Decimal(-1)})})
    with pytest.raises(ValidationError):
        diagnose_business(assemble_evidence(facts()), supplied)
