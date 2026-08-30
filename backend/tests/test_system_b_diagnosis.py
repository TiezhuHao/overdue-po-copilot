"""Fixed canonical fixtures only: no HTTP, database, generators or machine clock."""
import ast
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.system_b.models import (
    CanonicalPage, MaterialMpmContact, ProductConfig, StockpileRecord, StockpileSelection,
)
from app.system_b.diagnosis.assembler import assemble_evidence, EvidenceAssemblyError
from app.system_b.diagnosis.engine import diagnose
from app.system_b.diagnosis.models import (
    Completeness, DiagnosisStatus, EvidenceInputs, EvidenceKind as K, HistoricalStockpileQuery,
    MissingCode, RuleEvaluation, RuleState as S, SignalCode,
)
from app.system_b.diagnosis.rules import FOUNDATION_RULES, FORECAST_REDUCTION_RULE, OVERDUE_THRESHOLD_RULE
from tests.test_system_b_analytics import (
    DID, MID, PID, OID, SID, V1, V2, SNAPSHOT, monthly, purchase_order, supply, weekly, weeks,
)

HEADER, LINE, SUPPLIER, STOCK_VERSION, RECORD, CONFIG, EMPLOYEE = (UUID(int=i) for i in range(20, 27))


def po(**updates):
    return purchase_order(**({"po_header_id": HEADER, "po_line_id": LINE, "po_line_schedule_id": SID,
                              "material_id": MID, "organization_id": OID, "supplier_id": SUPPLIER,
                              "po_reference_project_id": PID} | updates))


def stockpile_query(*, count=1, version=True, **updates):
    fields = dict(dataset_version_id=DID, snapshot_date=SNAPSHOT, material_id=MID, material_code="MAT-TEST",
                  stockpile_version_name="history", stockpile_version_date=date(2024, 12, 31),
                  stockpile_tag="PLANNED", target_stockpile_qty=Decimal(20), actual_stockpile_qty=Decimal(10),
                  inventory_qty=Decimal(10), seven_day_demand_qty=Decimal(2), stockpile_qty_gap=Decimal(10),
                  stockpile_completion_ratio=Decimal("0.5"), agreement_unit_price=None,
                  future_months=(), inventory_age_quantities=(), stockpile_version_id=STOCK_VERSION,
                  stockpile_record_id=RECORD, stockpile_version_sequence=2, organization_id=OID)
    row = StockpileRecord(**(fields | updates))
    page = CanonicalPage[StockpileRecord](dataset_version_id=DID, snapshot_date=SNAPSHOT, page=1, page_size=100,
        total=count, items=(row,) if count else (), stockpile_selection=StockpileSelection(
            as_of_date=date(2025, 1, 1), stockpile_version_id=STOCK_VERSION if version else None,
            stockpile_version_date=date(2024, 12, 31) if version else None, sequence_no=2 if version else None))
    return HistoricalStockpileQuery(material_id=MID, as_of_date=date(2025, 1, 1), page=page)


def product(**updates):
    return ProductConfig(**(dict(dataset_version_id=DID, snapshot_date=SNAPSHOT, material_id=MID,
        material_code="MAT-TEST", project_id=PID, product_config_id=CONFIG, project_name="Synthetic Project",
        product_config_type="PRODUCT", product_config_name="Configuration", product_config_version="v1",
        product_config_status="ACTIVE", business_unit_name="Business", planning_department_name="Planning",
        lifecycle_stage="EOL", customer_code=None, customer_project_name=None, modified_at=None) | updates))


def full_inputs(**updates):
    values = dict(po=po(),
        weekly=weekly(material_id=MID, organization_id=OID, weekly_forecast_snapshot_id=UUID(int=30),
                      source_forecast_version_id=V2, forecast_snapshot_date=SNAPSHOT, weeks=weeks(dated=True)),
        supply=supply(material_id=MID, organization_id=OID, supply_demand_snapshot_id=UUID(int=31),
                      inventory_snapshot_id=UUID(int=32), supply_snapshot_date=SNAPSHOT, inventory_snapshot_date=SNAPSHOT,
                      mpm=MaterialMpmContact(employee_id=EMPLOYEE, employee_code="EMP", employee_name="Contact", department_name="Planning")),
        previous_forecast=monthly(forecast_version_sequence=1),
        current_forecast=monthly(V2, date(2026, 8, 10), "80", forecast_version_sequence=1),
        products=(product(),), stockpile=stockpile_query())
    return EvidenceInputs(**(values | updates))


def evaluate(inputs):
    return diagnose(assemble_evidence(inputs))


def test_complete_foundation_does_not_claim_a_final_cause():
    result = evaluate(full_inputs())
    assert result.completeness == Completeness.COMPLETE and result.status == DiagnosisStatus.FOUNDATION_ONLY
    assert result.primary_reason is None
    assert [item.rule_id for item in result.evaluations] == [rule.rule_id for rule in FOUNDATION_RULES]
    assert [item.state for item in result.evaluations] == [S.MATCHED] * 3
    assert result.signals == tuple(rule.signal for rule in FOUNDATION_RULES)
    assert result.missing_evidence == ()
    assert result.as_of_date == SNAPSHOT and result.dataset_version_id == DID


@pytest.mark.parametrize("delta,state", [(-1, S.NOT_MATCHED), (0, S.NOT_MATCHED), (1, S.MATCHED)])
def test_threshold_uses_signed_analytics_delta_and_strict_boundary(delta, state):
    # Ignore the existing R1 overdue_days/is_overdue display values.
    item = po(order_date=SNAPSHOT - timedelta(days=270 + delta), overdue_days=999, is_overdue=True)
    result = evaluate(EvidenceInputs(po=item))
    assert result.evaluations[0].state == state
    assert result.status == (DiagnosisStatus.NOT_ELIGIBLE if delta <= 0 else DiagnosisStatus.INSUFFICIENT_EVIDENCE)
    trace = {fact.evidence_id: fact for fact in result.evidence_trace}
    assert trace["aging.threshold_delta_days"].observed_value == delta


def test_invalid_date_or_missing_identity_cannot_be_eligible():
    for item in (po(order_date=SNAPSHOT + timedelta(days=1)), po(po_line_schedule_id=None)):
        result = evaluate(EvidenceInputs(po=item))
        assert result.evaluations[0].state == S.NOT_EVALUABLE
        assert result.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("old,new,state", [(100, 80, S.MATCHED), (100, 120, S.NOT_MATCHED),
                                           (100, 100, S.NOT_MATCHED), (0, 5, S.NOT_MATCHED), (0, 0, S.NOT_MATCHED)])
def test_forecast_rule_is_direction_only_including_zero_denominator(old, new, state):
    bundle = assemble_evidence(full_inputs(
        previous_forecast=monthly(quantity=str(old), forecast_version_sequence=1),
        current_forecast=monthly(V2, date(2026, 8, 10), str(new), forecast_version_sequence=1)))
    assert diagnose(bundle).evaluations[2].state == state
    if old == 0:
        assert bundle.analytics.forecast_change.forecast_change_rate is None


@pytest.mark.parametrize("updates", [
    {"current_forecast": None},
    {"current_forecast": monthly(V2, date(2026, 8, 3), forecast_version_sequence=2)},
    {"current_forecast": monthly(V2, date(2026, 8, 10), project_id=UUID(int=99), forecast_version_sequence=1)},
    {"current_forecast": monthly(V2, date(2026, 8, 10), forecast_month=date(2026, 10, 1), forecast_version_sequence=1)},
    {"current_forecast": monthly(V2, date(2026, 8, 10))},
])
def test_missing_or_incomparable_forecast_is_not_evaluable(updates):
    result = evaluate(full_inputs(**updates))
    assert result.evaluations[2].state == S.NOT_EVALUABLE
    assert result.evaluations[2].missing_evidence
    assert SignalCode.NEGATIVE_FORECAST_CHANGE not in result.signals


def test_missing_stockpile_is_unknown_but_verified_absence_is_not_matched():
    assert evaluate(full_inputs(stockpile=None)).evaluations[1].state == S.NOT_EVALUABLE
    for version in (True, False):
        result = evaluate(full_inputs(stockpile=stockpile_query(count=0, version=version)))
        assert result.evaluations[1].state == S.NOT_MATCHED
        fact = next(fact for fact in result.evidence_trace if fact.field == "record_count")
        assert fact.observed_value == 0 and fact.observed_on == po().order_date


@pytest.mark.parametrize("mode", ["no_selection", "partial_page", "page_two", "empty_tag", "missing_record_id"])
def test_incomplete_stockpile_cannot_prove_presence_or_absence(mode):
    query = stockpile_query()
    if mode == "no_selection":
        query = query.model_copy(update={"page": query.page.model_copy(update={"stockpile_selection": None})})
    elif mode == "partial_page":
        query = query.model_copy(update={"page": query.page.model_copy(update={"items": ()})})
    elif mode == "page_two":
        query = query.model_copy(update={"page": query.page.model_copy(update={"page": 2})})
    elif mode == "empty_tag":
        query = stockpile_query(stockpile_tag=" ")
    else:
        query = stockpile_query(stockpile_record_id=None)
    assert evaluate(full_inputs(stockpile=query)).evaluations[1].state == S.NOT_EVALUABLE


@pytest.mark.parametrize("field,value,code", [
    ("dataset_version_id", UUID(int=99), "DATASET_MISMATCH"),
    ("snapshot_date", date(2026, 8, 25), "SNAPSHOT_MISMATCH"),
    ("material_id", UUID(int=99), "MATERIAL_MISMATCH"),
    ("material_id", None, "MISSING_MATERIAL_JOIN_ID"),
    ("organization_id", UUID(int=99), "ORGANIZATION_MISMATCH"),
    ("forecast_snapshot_date", date(2026, 8, 27), "FUTURE_OBSERVATION"),
])
def test_scope_mismatches_fail_without_names_fallback(field, value, code):
    inputs = full_inputs()
    with pytest.raises(EvidenceAssemblyError, match=code):
        assemble_evidence(inputs.model_copy(update={"weekly": inputs.weekly.model_copy(update={field: value})}))


def test_forecast_schedule_and_stockpile_query_scope_are_checked():
    inputs = full_inputs()
    bad = inputs.current_forecast.model_copy(update={"po_line_schedule_id": UUID(int=99)})
    with pytest.raises(EvidenceAssemblyError, match="SCHEDULE_MISMATCH"):
        assemble_evidence(inputs.model_copy(update={"current_forecast": bad}))
    for change, code in (({"material_id": UUID(int=99)}, "MATERIAL_MISMATCH"),
                         ({"as_of_date": SNAPSHOT}, "NOT_ORDER_DATE"),
                         ({"requested_version_id": STOCK_VERSION}, "NOT_ORDER_DATE")):
        with pytest.raises(EvidenceAssemblyError, match=code):
            assemble_evidence(inputs.model_copy(update={"stockpile": inputs.stockpile.model_copy(update=change)}))


def test_future_or_wrong_stockpile_version_is_rejected():
    inputs = full_inputs()
    query = inputs.stockpile
    for updates in ({"stockpile_version_date": date(2025, 1, 2)}, {"stockpile_version_id": UUID(int=99)}):
        selection = query.page.stockpile_selection.model_copy(update=updates)
        altered = query.model_copy(update={"page": query.page.model_copy(update={"stockpile_selection": selection})})
        with pytest.raises(EvidenceAssemblyError):
            assemble_evidence(inputs.model_copy(update={"stockpile": altered}))


def test_provenance_preserves_inputs_of_derived_metric():
    result = evaluate(full_inputs())
    facts = {fact.evidence_id: fact for fact in result.evidence_trace}
    delta = facts["forecast_change.forecast_change_qty"]
    assert delta.source == "ANALYTICS" and delta.observed_value == Decimal(-20)
    assert delta.derived_from == ("previous.forecast_qty", "current.forecast_qty")
    for prefix, version in (("previous", V1), ("current", V2)):
        fact = facts[f"{prefix}.forecast_qty"]
        assert fact.source == "R3" and fact.version_sequence == 1
        assert fact.dataset_version_id == DID and fact.snapshot_date == SNAPSHOT
        assert fact.period == date(2026, 9, 1)
        keys = {key.name: key.value for key in fact.entity_keys}
        assert keys["forecast_version_id"] == version and keys["project_id"] == PID and keys["material_id"] == MID
    stock = facts[f"stockpile.{RECORD}.stockpile_tag"]
    assert stock.source == "R6" and stock.version_date == date(2024, 12, 31) and stock.version_sequence == 2
    assert stock.observed_value == "PLANNED"
    assert {key.name: key.value for key in stock.entity_keys}["stockpile_record_id"] == RECORD


@dataclass(frozen=True)
class HistoricalLifecycleProbe:
    rule_id: str = "historical_lifecycle_probe"
    version: str = "test-only"
    semantic_label: str = "HISTORICAL_REQUIREMENT"
    required_evidence: tuple = (K.HISTORICAL_LIFECYCLE,)

    def evaluate(self, bundle):
        pytest.fail("Historical lifecycle predicate must never run without historical evidence")


def test_current_lifecycle_never_satisfies_historical_requirement():
    bundle = assemble_evidence(full_inputs())
    assert bundle.fact_ids(K.CURRENT_LIFECYCLE)
    assert bundle.missing_for((K.HISTORICAL_LIFECYCLE,))[0].code == MissingCode.HISTORICAL_LIFECYCLE_UNAVAILABLE
    result = diagnose(bundle, rules=(HistoricalLifecycleProbe(),))
    assert result.evaluations[0].state == S.NOT_EVALUABLE and result.completeness == Completeness.PARTIAL


def test_reference_project_does_not_constrain_forecast_project_or_become_responsibility():
    inputs = full_inputs(po=po(po_reference_project_id=UUID(int=99)))
    result = evaluate(inputs)
    assert result.evaluations[2].state == S.MATCHED and result.primary_reason is None
    assert {key.name: key.value for key in result.entity_keys}["po_reference_project_id"] == UUID(int=99)
    rendered = result.model_dump_json()
    assert all(name not in rendered for name in ("responsible_project", "demand_owner", "root_cause_project",
                                                "recommended_action", "cancel_po", "reschedule_po", "confidence"))


def test_weekly_contributions_and_material_mpm_keep_their_own_identity():
    from app.system_b.models import ProjectWeekForecast
    inputs = full_inputs()
    rows = tuple(ProjectWeekForecast(**week.model_dump(), project_id=PID) for week in inputs.weekly.weeks)
    bundle = assemble_evidence(inputs.model_copy(update={"weekly": inputs.weekly.model_copy(update={"project_contributions": rows})}))
    contribution = next(fact for fact in bundle.facts if fact.kind == K.PROJECT_CONTRIBUTION and fact.period is not None)
    keys = {key.name: key.value for key in contribution.entity_keys}
    assert keys["material_id"] == MID and keys["project_id"] == PID
    assert keys["weekly_forecast_snapshot_id"] == UUID(int=30)
    contact = next(fact for fact in bundle.facts if fact.kind == K.MPM)
    assert contact.observed_value == EMPLOYEE and "project_id" not in {key.name for key in contact.entity_keys}


def test_determinism_and_ambient_decimal_context():
    inputs = full_inputs()
    expected = evaluate(inputs).model_dump_json()
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_UP
        ctx.traps[Inexact] = True
        assert evaluate(inputs).model_dump_json() == expected
    assert evaluate(inputs).model_dump_json() == expected


@pytest.mark.parametrize("mutation", ["analytics", "provenance", "missing"])
def test_engine_rejects_forged_or_stale_bundle(mutation):
    bundle = assemble_evidence(full_inputs())
    if mutation == "analytics":
        aging = bundle.analytics.aging.model_copy(update={"threshold_delta_days": -1})
        bundle = bundle.model_copy(update={"analytics": bundle.analytics.model_copy(update={"aging": aging})})
    elif mutation == "provenance":
        bundle = bundle.model_copy(update={"facts": bundle.facts[1:]})
    else:
        bundle = bundle.model_copy(update={"missing_evidence": ()})
    with pytest.raises(EvidenceAssemblyError, match="BUNDLE_DERIVATION_MISMATCH"):
        diagnose(bundle)


def test_registry_rejects_duplicates_and_bad_evidence_references():
    bundle = assemble_evidence(full_inputs())
    with pytest.raises(ValueError, match="INVALID_RULE_REGISTRY"):
        diagnose(bundle, rules=(OVERDUE_THRESHOLD_RULE, OVERDUE_THRESHOLD_RULE))
    with pytest.raises(ValueError, match="INVALID_RULE_REGISTRY"):
        diagnose(bundle, rules=())
    bad = replace(FORECAST_REDUCTION_RULE, used_fields=("not_a_field",))
    with pytest.raises(ValueError, match="INVALID_RULE_EVIDENCE_REFERENCE"):
        diagnose(bundle, rules=(bad,))


def test_dependency_boundary_and_no_clock_or_final_cause_fields():
    root = Path(__file__).resolve().parents[1] / "app/system_b/diagnosis"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("httpx", "requests", "sqlalchemy", "app.db", "app.api",
                    "app.services", "app.models", "app.system_b.adapters", "app.core", "openai", "langgraph"))
            if isinstance(node, ast.Import):
                assert all(not item.name.startswith(("httpx", "requests", "sqlalchemy", "openai", "langgraph")) for item in node.names)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"now", "today", "utcnow"}
    with pytest.raises(ValidationError):
        full_inputs().model_validate(full_inputs().model_dump() | {"historical_lifecycle": product()})
