"""Pure, fixed-date analytics tests: no HTTP, database or machine clock."""

import ast
from datetime import date, datetime, timedelta
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.system_b.analytics.calculations import (
    calculate_consumption, calculate_coverage, calculate_forecast_change,
    calculate_forecast_window, calculate_po_aging, calculate_po_consumption, calculate_supply_demand,
)
from app.system_b.analytics.models import Availability as A, ReasonCode as R
from app.system_b.analytics.service import AnalyticsService
from app.system_b.models import (
    ForecastSnapshot, MaterialMpmContact, MaterialSupplyDemand, PurchaseOrder,
    WeekForecast, WeeklyForecastSnapshot,
)


DID, MID, PID, OID, SID, V1, V2 = [UUID(int=index) for index in range(1, 8)]
SNAPSHOT = date(2026, 8, 26)


def weeks(qty="2", count=13, dated=False):
    return tuple(WeekForecast(week_index=i, forecast_qty=Decimal(qty),
                             week_start_date=date(2026, 8, 31) + timedelta(weeks=i - 1) if dated else None)
                 for i in range(1, count + 1))


def weekly(**updates):
    fields = dict(dataset_version_id=DID, snapshot_date=SNAPSHOT, material_code="MAT-TEST",
                  material_id=None, organization_id=None, organization_code="INV-TEST", weeks=weeks(),
                  thirteen_week_demand_qty=Decimal(26), weekly_average_demand_qty=Decimal(2),
                  open_po_qty=Decimal(10), advance_shipping_notice_qty=None, open_purchase_requisition_qty=None,
                  good_subinventory_qty=Decimal(6), defective_subinventory_qty=Decimal(1), top_project=None)
    return WeeklyForecastSnapshot(**(fields | updates))


def purchase_order(**updates):
    fields = dict(dataset_version_id=DID, snapshot_date=SNAPSHOT, material_code="MAT-TEST",
                  po_number="PO-TEST", po_line_number=1, shipment_number=2,
                  inventory_organization_code="INV-TEST", inventory_organization_type="MASS_PRODUCTION",
                  supplier_code="SUP-TEST", supplier_name="Synthetic Supplier", reference_project_code=None,
                  reference_project_name=None, order_date=date(2025, 1, 1), due_date=date(2025, 1, 31),
                  material_lt_days=30, schedule_qty=Decimal(15), schedule_received_qty=Decimal(5),
                  overdue_open_qty=Decimal(10), overdue_days=332, is_overdue=True, po_status="OPEN",
                  close_status="OPEN", can_close=False, completion_at=None)
    return PurchaseOrder(**(fields | updates))


def supply(**updates):
    fields = dict(dataset_version_id=DID, snapshot_date=SNAPSHOT, material_code="MAT-TEST",
                  inventory_organization_code="INV-TEST", material_lt_days=30,
                  all_supply_qty=Decimal(50), actual_demand_total_qty=Decimal(30),
                  supply_demand_surplus_qty=Decimal(20), good_non_vmi_inventory_qty=Decimal(10),
                  defective_inventory_qty=Decimal(2), non_mrp_inventory_qty=Decimal(3),
                  non_vmi_in_transit_order_qty=Decimal(32), non_vmi_in_transit_delivery_qty=Decimal(8),
                  open_po_qty=Decimal(40), purchase_requisition_qty=None,
                  organization_active_projects=None, enterprise_active_projects=None, top_project=None,
                  mpm=MaterialMpmContact(employee_code="EMP-TEST", employee_name="Synthetic Contact",
                                         department_name="Planning"))
    return MaterialSupplyDemand(**(fields | updates))


def monthly(version_id=V1, version_date=date(2026, 8, 3), quantity="100", **updates):
    # Explicit canonical IDs exercise the conditional primitive, not a fictitious REST API.
    fields = dict(dataset_version_id=DID, snapshot_date=SNAPSHOT, material_id=MID, project_id=PID,
                  material_code="MAT-TEST", project_name="Synthetic Project", po_line_schedule_id=SID,
                  forecast_version_id=version_id, forecast_version_name="test-version",
                  forecast_version_date=version_date, window_role="BASELINE",
                  forecast_month=date(2026, 9, 1), forecast_qty=Decimal(quantity),
                  forecast_total_qty=Decimal(700), cumulative_shipped_qty=Decimal(5))
    return ForecastSnapshot(**(fields | updates))


@pytest.mark.parametrize("offset,expected_to,expected_beyond", [
    (-110, 110, 0), (-1, 1, 0), (0, 0, 0), (1, 0, 1), (80, 0, 80),
])
def test_po_aging_threshold_boundaries(offset, expected_to, expected_beyond):
    ordered = date(2024, 1, 1)
    result = calculate_po_aging(ordered, 90, as_of_date=ordered + timedelta(days=330 + offset))
    assert result.status == A.AVAILABLE and result.threshold_days == 330
    assert result.po_age_days == 330 + offset
    assert result.threshold_delta_days == offset
    assert result.days_to_threshold == expected_to and result.days_beyond_threshold == expected_beyond
    assert result.days_to_threshold >= 0 and result.days_beyond_threshold >= 0
    assert result.threshold_date == ordered + timedelta(days=330)


def test_po_aging_leap_day_and_year_boundary():
    for ordered, as_of, expected_age in (
        (date(2024, 2, 28), date(2024, 3, 1), 2),
        (date(2023, 12, 31), date(2024, 1, 1), 1),
    ):
        result = calculate_po_aging(ordered, 0, as_of_date=as_of)
        assert result.po_age_days == expected_age
        assert result.threshold_delta_days == expected_age - 240
        assert result.days_to_threshold == 240 - expected_age
        assert result.days_beyond_threshold == 0


@pytest.mark.parametrize("ordered,lt,as_of,reason", [
    (None, 30, SNAPSHOT, R.MISSING_REQUIRED_FIELD),
    (date(2025, 1, 1), None, SNAPSHOT, R.MISSING_REQUIRED_FIELD),
    (date(2025, 1, 1), 30, None, R.MISSING_REQUIRED_FIELD),
    (date(2027, 1, 1), 30, SNAPSHOT, R.INVALID_INPUT),
    (date(2025, 1, 1), -1, SNAPSHOT, R.INVALID_INPUT),
    (date(2025, 1, 1), True, SNAPSHOT, R.INVALID_INPUT),
    (datetime(2025, 1, 1), 30, SNAPSHOT, R.INVALID_INPUT),
    (date(9999, 12, 31), 0, date(9999, 12, 31), R.INVALID_INPUT),
])
def test_po_aging_missing_invalid_and_overflow(ordered, lt, as_of, reason):
    result = calculate_po_aging(ordered, lt, as_of_date=as_of)
    assert result.status == A.NOT_COMPUTABLE and result.reason_codes == (reason,)
    assert result.po_age_days is result.threshold_days is result.days_beyond_threshold is None
    assert result.threshold_delta_days is result.days_to_threshold is None


def test_forecast_aggregate_by_index_not_input_order_or_source_summary():
    row = weekly(weeks=tuple(reversed(weeks())), thirteen_week_demand_qty=Decimal(999))
    result = calculate_forecast_window(row.weeks)
    assert result.status == A.AVAILABLE and result.observed_week_count == 13
    assert result.total_forecast_qty == 26 and result.average_weekly_demand_qty == 2
    assert result.window_start_date is result.window_end_date_exclusive is None


def test_calendar_dates_only_when_explicit_complete_monday_sequence():
    result = calculate_forecast_window(weeks(dated=True))
    assert result.window_start_date == date(2026, 8, 31)
    assert (result.window_end_date_exclusive - result.window_start_date).days == 91
    incomplete = list(weeks(dated=True))
    incomplete[3] = WeekForecast(week_index=4, forecast_qty=Decimal(2))
    result = calculate_forecast_window(incomplete)
    assert result.status == A.PARTIAL and result.total_forecast_qty is None
    invalid = list(weeks(dated=True))
    invalid[3] = WeekForecast(week_index=4, forecast_qty=Decimal(2), week_start_date=date(2026, 9, 22))
    assert calculate_forecast_window(invalid).reason_codes == (R.INVALID_FORECAST_WINDOW,)


def test_incomplete_window_keeps_observed_total_but_does_not_extrapolate():
    result = calculate_forecast_window(weeks(count=12))
    assert result.status == A.PARTIAL and result.observed_forecast_qty == 24
    assert result.total_forecast_qty is result.average_weekly_demand_qty is None
    assert calculate_forecast_window(()).status == A.NOT_COMPUTABLE
    assert calculate_forecast_window(None).reason_codes == (R.MISSING_FORECAST,)


def test_duplicate_week_is_rejected_even_when_there_are_thirteen_entries():
    duplicate = weeks(count=12) + (WeekForecast(week_index=12, forecast_qty=Decimal(2)),)
    assert len(duplicate) == 13
    result = calculate_forecast_window(duplicate)
    assert result.reason_codes == (R.INVALID_FORECAST_WINDOW,)
    assert result.observed_week_count == 13
    assert result.total_forecast_qty is result.average_weekly_demand_qty is None


def test_negative_and_nullable_week_quantities_are_not_zero_filled():
    assert calculate_forecast_window(weeks(qty="-1")).reason_codes == (R.INVALID_INPUT,)
    with pytest.raises(ValidationError):
        WeekForecast(week_index=1, forecast_qty=None)
    with pytest.raises(ValidationError):
        weekly(weeks=weeks(count=12))


@pytest.mark.parametrize("quantity,expected", [(Decimal(10), Decimal(5)), (Decimal(0), Decimal(0)), (Decimal("0.125"), Decimal("0.0625"))])
def test_consumption_normal_zero_and_decimal(quantity, expected):
    result = calculate_consumption(quantity, weeks())
    assert result.status == A.AVAILABLE and result.estimated_consumption_weeks == expected


@pytest.mark.parametrize("quantity", [Decimal(0), Decimal(10)])
def test_zero_demand_never_becomes_infinity_or_zero_ratio(quantity):
    result = calculate_consumption(quantity, weeks(qty="0"))
    assert result.status == A.PARTIAL and result.forecast.total_forecast_qty == 0
    assert result.estimated_consumption_weeks is None and R.NO_FORECAST_DEMAND in result.reason_codes


@pytest.mark.parametrize("buckets,reason", [(None, R.MISSING_FORECAST), (weeks(count=12), R.INCOMPLETE_FORECAST_WINDOW)])
def test_missing_partial_forecast_does_not_produce_consumption(buckets, reason):
    result = calculate_consumption(Decimal(10), buckets)
    assert result.estimated_consumption_weeks is None and reason in result.reason_codes


@pytest.mark.parametrize("quantity,reason", [
    (None, R.MISSING_REQUIRED_FIELD), (Decimal(-1), R.INVALID_INPUT),
    (Decimal("NaN"), R.INVALID_INPUT), (Decimal("Infinity"), R.INVALID_INPUT), (1.5, R.INVALID_INPUT),
])
def test_invalid_nullable_consumption_quantity(quantity, reason):
    result = calculate_consumption(quantity, weeks())
    assert result.estimated_consumption_weeks is None and result.reason_codes == (reason,)
    assert result.open_qty is None


def test_decimal_calculations_ignore_ambient_precision_rounding_and_traps():
    buckets = (WeekForecast(week_index=1, forecast_qty=Decimal(3)),) + tuple(
        WeekForecast(week_index=i, forecast_qty=Decimal(0)) for i in range(2, 14))
    expected = calculate_consumption(Decimal(1), buckets)
    with localcontext() as ambient:
        ambient.prec = 2
        ambient.rounding = ROUND_UP
        ambient.traps[Inexact] = True
        before = (ambient.prec, ambient.rounding, dict(ambient.traps), dict(ambient.flags))
        actual = calculate_consumption(Decimal(1), buckets)
        assert (ambient.prec, ambient.rounding, dict(ambient.traps), dict(ambient.flags)) == before
    assert actual == expected
    assert actual.estimated_consumption_weeks == Decimal("4.333333333333333333333333333333333333333")


@pytest.mark.parametrize("supply_qty,demand,expected", [(50, 30, 20), (20, 30, -10), (30, 30, 0)])
def test_established_supply_surplus_shortage_and_zero(supply_qty, demand, expected):
    result = calculate_supply_demand(supply(all_supply_qty=Decimal(supply_qty), actual_demand_total_qty=Decimal(demand)))
    assert result.supply_demand_surplus_qty == expected
    assert result.status == A.PARTIAL and R.UNCONFIRMED_SUPPLY_COMPOSITION in result.reason_codes


def test_pr_is_not_added_to_actual_supply_or_relabelled_as_confirmed():
    without_pr = calculate_supply_demand(supply())
    with_pr = calculate_supply_demand(supply(purchase_requisition_qty=Decimal(100)))
    assert without_pr.purchase_requisition_qty is None and with_pr.purchase_requisition_qty == 100
    assert without_pr.supply_demand_surplus_qty == with_pr.supply_demand_surplus_qty == 20
    assert with_pr.confirmed_supply_qty is with_pr.planned_supply_qty is None
    assert with_pr.confirmed_gap_qty is with_pr.planned_gap_qty is None


def test_supply_missing_invalid_and_independently_invalid_pr():
    assert calculate_supply_demand(None).status == A.NOT_COMPUTABLE
    assert calculate_supply_demand(supply(all_supply_qty=Decimal(-1))).status == A.NOT_COMPUTABLE
    result = calculate_supply_demand(supply(purchase_requisition_qty=Decimal(-1)))
    assert result.supply_demand_surplus_qty == 20 and result.purchase_requisition_qty is None
    assert R.INVALID_INPUT in result.reason_codes
    with pytest.raises(ValidationError):
        supply(actual_demand_total_qty=None)


def test_inventory_coverage_and_blocked_confirmed_planned_coverage():
    result = calculate_coverage(Decimal(6), weeks())
    assert result.inventory_coverage_weeks == 3 and result.status == A.PARTIAL
    assert result.confirmed_supply_coverage_weeks is result.planned_supply_coverage_weeks is None
    assert calculate_coverage(Decimal(0), weeks()).inventory_coverage_weeks == 0


@pytest.mark.parametrize("inventory,buckets,reason", [
    (Decimal(6), weeks(qty="0"), R.NO_FORECAST_DEMAND),
    (Decimal(6), None, R.MISSING_FORECAST),
    (Decimal(6), weeks(count=12), R.INCOMPLETE_FORECAST_WINDOW),
    (None, weeks(), R.MISSING_REQUIRED_FIELD),
    (Decimal(-1), weeks(), R.INVALID_INPUT),
])
def test_coverage_unavailable_inputs(inventory, buckets, reason):
    result = calculate_coverage(inventory, buckets)
    assert result.inventory_coverage_weeks is None and reason in result.reason_codes


@pytest.mark.parametrize("quantity,change,rate", [("125", "25", "0.25"), ("38", "-62", "-0.62"), ("100", "0", "0")])
def test_explicit_month_comparison_increase_decrease_unchanged(quantity, change, rate):
    result = calculate_forecast_change(monthly(), monthly(V2, date(2026, 8, 10), quantity))
    assert result.status == A.AVAILABLE and result.forecast_change_qty == Decimal(change)
    assert result.forecast_change_rate == Decimal(rate)
    assert result.previous_forecast_qty == 100  # Not the repeated seven-month total (700).


@pytest.mark.parametrize("current", ["0", "100"])
def test_previous_zero_retains_change_but_rate_is_unavailable(current):
    result = calculate_forecast_change(monthly(quantity="0"), monthly(V2, date(2026, 8, 10), current))
    assert result.status == A.PARTIAL and result.forecast_change_qty == Decimal(current)
    assert result.forecast_change_rate is None and result.reason_codes == (R.ZERO_DENOMINATOR,)


@pytest.mark.parametrize("update", [
    {"material_id": UUID(int=100)}, {"project_id": UUID(int=100)}, {"dataset_version_id": UUID(int=100)},
    {"snapshot_date": date(2026, 8, 25)}, {"forecast_month": date(2026, 10, 1)},
    {"po_line_schedule_id": UUID(int=100)},
])
def test_mismatched_material_project_horizon_and_scope(update):
    result = calculate_forecast_change(monthly(), monthly(V2, date(2026, 8, 10), **update))
    assert result.status == A.NOT_COMPUTABLE and R.INCOMPATIBLE_SCOPE in result.reason_codes
    assert result.forecast_change_qty is result.forecast_change_rate is None


@pytest.mark.parametrize("version_day", [date(2026, 8, 2), date(2026, 8, 3), date(2026, 9, 1)])
def test_reversed_same_day_or_future_version_not_inferred(version_day):
    result = calculate_forecast_change(monthly(), monthly(V2, version_day))
    assert result.reason_codes == (R.INCOMPARABLE_FORECAST_VERSIONS,)


def test_actual_rest_missing_ids_blocks_comparison_and_names_do_not_resolve_it():
    previous = monthly(material_id=None, project_id=None, forecast_version_id=None)
    current = monthly(V2, date(2026, 8, 10), material_id=None, project_id=None, forecast_version_id=None)
    result = calculate_forecast_change(previous, current)
    assert result.status == A.NOT_COMPUTABLE and R.MISSING_STABLE_ID in result.reason_codes
    assert calculate_forecast_change(None, current).reason_codes == (R.MISSING_FORECAST,)


def test_same_version_id_and_negative_forecast_are_rejected():
    assert calculate_forecast_change(monthly(), monthly(V1, date(2026, 8, 10))).status == A.NOT_COMPUTABLE
    assert calculate_forecast_change(monthly(), monthly(V2, date(2026, 8, 10), "-1")).reason_codes == (R.INVALID_INPUT,)


def test_service_uses_snapshot_and_keeps_material_and_schedule_quantity_scopes_separate():
    po = purchase_order(overdue_days=999)
    result = AnalyticsService.analyze_purchase_order(po, weekly())
    assert result.aging.as_of_date == SNAPSHOT and result.aging.days_beyond_threshold == 332
    assert result.shipment_number == 2
    assert result.consumption.status == A.NOT_COMPUTABLE and R.MISSING_STABLE_ID in result.consumption.reason_codes
    material = AnalyticsService.analyze_material_forecast(weekly())
    assert material.consumption.estimated_consumption_weeks == 5
    assert material.coverage.inventory_coverage_weeks == 3
    assert material.material_id is None  # No guessed join required for a single source row.


def test_po_consumption_requires_matching_stable_scope():
    po = purchase_order(material_id=MID, organization_id=OID, overdue_open_qty=Decimal(4))
    forecast = weekly(material_id=MID, organization_id=OID)
    assert calculate_po_consumption(po, forecast).estimated_consumption_weeks == 2
    assert calculate_po_consumption(po, None).reason_codes == (R.MISSING_FORECAST,)
    assert calculate_po_consumption(po, weekly(material_id=PID, organization_id=OID)).reason_codes == (R.INCOMPATIBLE_SCOPE,)
    assert calculate_po_consumption(po, weekly(snapshot_date=date(2026, 8, 25))).reason_codes == (R.INCOMPATIBLE_SCOPE,)


def test_analytics_has_no_http_database_clock_or_adapter_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "system_b" / "analytics"
    forbidden_imports = ("httpx", "requests", "sqlalchemy", "app.db", "app.models", "app.core",
                         "app.system_b.adapters", "app.generators", "app.reporting", "app.domain")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [node.module or ""] if isinstance(node, ast.ImportFrom) else (
                [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            assert not any(name.startswith(forbidden_imports) for name in names), path.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"now", "today", "utcnow"}, path.name
    result = AnalyticsService.analyze_material_forecast(weekly()).model_dump_json()
    assert not any(word in result for word in ("cause_type", "responsible_project", "expected_action", "Infinity", "NaN"))
