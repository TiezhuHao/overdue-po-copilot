"""Deterministic HTTP contract tests; no running server or database required."""

import ast
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.system_b.adapters.errors import (
    SystemAHTTPError, SystemANotFoundError, SystemAResponseValidationError, SystemAUnavailableError,
)
from app.system_b.adapters.system_a import SystemAAdapter
from app.system_b.models import (
    ForecastSnapshot, MaterialSupplyDemand, ProductConfig, PurchaseOrder, StockpileRecord,
    WeeklyForecastSnapshot,
)


DID = UUID("bb400de1-d2f8-4421-b635-27d2c88f2000")
OTHER_DID = UUID("bb400de1-d2f8-4421-b635-27d2c88f2001")
SCHEDULE_ID = UUID("bb400de1-d2f8-4421-b635-27d2c88f2002")
SNAPSHOT = "2026-08-26"
REPORTS = [
    (1, "purchase_orders", "overdue-pos", PurchaseOrder),
    (2, "material_supply_demand", "material-supply-demand", MaterialSupplyDemand),
    (3, "forecast_history", "forecast-history", ForecastSnapshot),
    (4, "latest_13w_forecast", "latest-13w-forecast", WeeklyForecastSnapshot),
    (5, "product_configurations", "product-configurations", ProductConfig),
    (6, "stockpile", "stockpile", StockpileRecord),
]


def source_row(report_id):
    common = {"material_code": "MAT-TEST-001"}
    if report_id == 1:
        return common | {
            "po_number": "PO-TEST-001", "po_line_number": 2, "shipment_number": 3,
            "inventory_organization_code": "INV-TEST", "inventory_organization_type": "MASS_PRODUCTION",
            "supplier_code": "SUP-TEST", "supplier_name": "Synthetic Supplier",
            "reference_project_code": None, "reference_project_name": None,
            "order_date": "2025-01-01", "due_date": "2025-01-31", "snapshot_date": SNAPSHOT,
            "material_lt_days": 30, "schedule_qty": "15.2500", "schedule_received_qty": "5.1250",
            "overdue_open_qty": "10.1250", "overdue_days": 332, "is_overdue": True,
            "po_status": "PARTIALLY_RECEIVED", "close_status": "OPEN", "can_close": False,
            "completion_at": None,
        }
    if report_id == 2:
        return common | {
            "inventory_organization_code": "INV-TEST", "material_lt_days": 30,
            "all_supply_qty": "30.1000", "actual_demand_total_qty": "40.2000",
            "supply_demand_surplus_qty": "-10.1000", "good_non_vmi_inventory_qty": "10",
            "defective_inventory_qty": "2", "non_mrp_inventory_qty": "3",
            "non_vmi_in_transit_order_qty": "12", "non_vmi_in_transit_delivery_qty": "8",
            "open_po_qty": "20", "purchase_requisition_qty": None,
            "organization_active_projects": ["Synthetic Project"], "enterprise_active_projects": None,
            "top_project": None, "mpm_code": "EMP-TEST", "mpm_name": "Synthetic Contact",
            "mpm_department_name": "Planning",
        }
    if report_id == 3:
        return common | {
            "po_line_schedule_id": str(SCHEDULE_ID), "project_name": "Synthetic Project",
            "forecast_version_name": "forecast-test-v1", "forecast_version_date": "2025-01-27",
            "window_role": "BASELINE", "forecast_month": "2025-02-01", "forecast_qty": "12.1250",
            "forecast_total_qty": "85.0000", "cumulative_shipped_qty": "7.5000",
        }
    if report_id == 4:
        return common | {
            "organization_code": "INV-TEST", "snapshot_date": SNAPSHOT,
            **{f"week_{index:02d}_forecast_qty": "0" for index in range(1, 14)},
            "thirteen_week_demand_qty": "0", "weekly_average_demand_qty": "0", "open_po_qty": "20",
            "advance_shipping_notice_qty": None, "open_purchase_requisition_qty": None,
            "good_subinventory_qty": "10", "defective_subinventory_qty": "2", "top_project": None,
        }
    if report_id == 5:
        return common | {
            "project_name": "Synthetic Project", "product_config_type": "STANDARD",
            "product_config_name": "Synthetic Config", "product_config_version": "v1",
            "product_config_status": "ACTIVE", "business_unit_name": "Business Unit",
            "planning_department_name": "Planning", "lifecycle_stage": "EOL",
            "customer_code": None, "customer_project_name": None, "modified_at": "2026-08-01T08:00:00+08:00",
        }
    return common | {
        "stockpile_version_name": "stockpile-test-v1", "stockpile_version_date": "2026-08-25",
        "stockpile_nature": "PLANNED", "planned_stockpile_qty": "0", "inventory_qty": "0",
        "seven_day_demand_qty": "0", "stockpile_qty_gap": "0", "stockpile_completion_ratio": None,
        "agreement_unit_price": "1.2345",
        "future_months": [{"period": f"2026-{month:02d}-01", "quantity": "0"} for month in range(9, 13)]
                         + [{"period": f"2027-{month:02d}-01", "quantity": "0"} for month in (1, 2)],
        "inventory_age_quantities": [{"threshold_days": 30, "quantity": "4"},
                                     {"threshold_days": 60, "quantity": "2"}],
    }


def envelope(items, **overrides):
    return {"dataset_version_id": str(DID), "snapshot_date": SNAPSHOT, "page": 1,
            "page_size": 100, "total": len(items), "items": items} | overrides


def adapter_for(handler):
    return SystemAAdapter(
        Settings(_env_file=None, system_a_base_url="https://enterprise.invalid/custom/api/v1",
                 system_a_timeout_seconds=2.5), transport=httpx.MockTransport(handler),
    )


def fetch(report_id, body):
    with adapter_for(lambda request: httpx.Response(200, json=body)) as adapter:
        return getattr(adapter, REPORTS[report_id - 1][1])(DID)


@pytest.mark.parametrize("report_id,method,path,model", REPORTS)
def test_six_normal_responses_and_explicit_context(report_id, method, path, model):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=envelope([source_row(report_id)]))

    with adapter_for(handler) as adapter:
        page = getattr(adapter, method)(DID, material_code="MAT-TEST-001")
    assert len(requests) == 1
    assert requests[0].url.path == f"/custom/api/v1/reports/{path}"
    assert dict(requests[0].url.params) == {
        "dataset_version_id": str(DID), "page": "1", "page_size": "100", "material_code": "MAT-TEST-001",
    }
    assert requests[0].extensions["timeout"] == dict.fromkeys(("connect", "read", "write", "pool"), 2.5)
    assert len(page.items) == page.total == 1
    assert isinstance(page.items[0], model)
    assert page.items[0].dataset_version_id == DID and page.items[0].snapshot_date == date(2026, 8, 26)
    assert page.items[0].material_id is None


@pytest.mark.parametrize("report_id,method,path,model", REPORTS)
def test_empty_is_success_only_for_valid_response(report_id, method, path, model):
    result = fetch(report_id, envelope([]))
    assert result.items == () and result.total == 0


@pytest.mark.parametrize("status,error", [
    (404, SystemANotFoundError), (500, SystemAUnavailableError), (503, SystemAUnavailableError),
    (400, SystemAHTTPError), (401, SystemAHTTPError), (403, SystemAHTTPError),
    (422, SystemAHTTPError), (429, SystemAHTTPError), (302, SystemAHTTPError), (204, SystemAHTTPError),
])
def test_status_errors_are_typed_sanitized_and_not_retried(status, error):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"location": "https://redirect.invalid"},
                              json={"detail": "sensitive-upstream-body"})

    with adapter_for(handler) as adapter, pytest.raises(error) as caught:
        adapter.purchase_orders(DID)
    assert caught.value.status_code == status
    assert "sensitive-upstream-body" not in str(caught.value)
    assert len(requests) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout])
def test_transport_errors(error):
    def handler(request):
        raise error("sensitive-connection-text", request=request)

    with adapter_for(handler) as adapter, pytest.raises(SystemAUnavailableError) as caught:
        adapter.purchase_orders(DID)
    assert "sensitive" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("body", [b"not-json", b"null", b"[]", b"{}", b"\xff"])
def test_malformed_json_or_envelope(body):
    with adapter_for(lambda request: httpx.Response(200, content=body)) as adapter:
        with pytest.raises(SystemAResponseValidationError):
            adapter.purchase_orders(DID)


@pytest.mark.parametrize("report_id,method,path,model", REPORTS)
def test_required_field_missing_or_null_is_not_an_empty_result(report_id, method, path, model):
    row = source_row(report_id)
    row.pop("material_code")
    with pytest.raises(SystemAResponseValidationError):
        fetch(report_id, envelope([row]))
    row["material_code"] = None
    with pytest.raises(SystemAResponseValidationError):
        fetch(report_id, envelope([row]))


@pytest.mark.parametrize("field,value", [
    ("schedule_qty", "not-a-number"), ("schedule_qty", "NaN"), ("schedule_qty", "Infinity"),
    ("schedule_qty", True), ("material_lt_days", True), ("material_lt_days", -1),
    ("order_date", "2026-02-30"), ("order_date", 0), ("order_date", "0"),
    ("order_date", "2026-08-26T00:00:00"), ("completion_at", "2026-01-01T00:00:00"),
])
def test_invalid_consumed_scalar_types(field, value):
    row = source_row(1) | {field: value}
    with pytest.raises(SystemAResponseValidationError):
        fetch(1, envelope([row]))


def test_nullable_dates_decimal_and_schedule_grain():
    row = fetch(1, envelope([source_row(1)])).items[0]
    assert (row.po_number, row.po_line_number, row.shipment_number) == ("PO-TEST-001", 2, 3)
    assert row.schedule_qty == Decimal("15.2500")
    assert row.schedule_received_qty == Decimal("5.1250")
    assert row.overdue_open_qty == Decimal("10.1250")
    assert row.order_date == date(2025, 1, 1) and row.completion_at is None
    assert row.reference_project_code is row.po_line_schedule_id is row.unit_price is row.currency is None
    completed = fetch(1, envelope([source_row(1) | {"completion_at": "2026-08-01T00:00:00Z"}])).items[0]
    assert completed.completion_at.utcoffset().total_seconds() == 0


def test_json_numeric_decimal_is_not_rounded_through_float():
    body = json.dumps(envelope([source_row(1) | {"schedule_qty": "DECIMAL_PLACEHOLDER"}]))
    body = body.replace('"DECIMAL_PLACEHOLDER"', "1234567890123456.1234")
    with adapter_for(lambda request: httpx.Response(200, text=body)) as adapter:
        row = adapter.purchase_orders(DID).items[0]
    assert row.schedule_qty == Decimal("1234567890123456.1234")


def test_supply_mpm_and_source_component_semantics_preserved():
    row = fetch(2, envelope([source_row(2)])).items[0]
    assert row.mpm.employee_code == "EMP-TEST" and row.mpm.employee_id is None
    assert row.organization_active_projects == ("Synthetic Project",)
    assert row.enterprise_active_projects is None
    assert row.supply_demand_surplus_qty == Decimal("-10.1")
    assert row.non_vmi_in_transit_order_qty == 12 and row.non_vmi_in_transit_delivery_qty == 8
    assert row.open_po_qty == 20 and row.purchase_requisition_qty is None


def test_monthly_forecast_keeps_schedule_and_version_separate():
    row = fetch(3, envelope([source_row(3)])).items[0]
    assert row.po_line_schedule_id == SCHEDULE_ID and row.dataset_version_id == DID
    assert row.forecast_version_date == date(2025, 1, 27) and row.forecast_month == date(2025, 2, 1)
    assert row.forecast_qty == Decimal("12.1250") and row.forecast_total_qty == 85
    assert row.project_id is row.forecast_version_id is None


def test_week_slots_preserve_zero_demand_without_fabricated_dates():
    row = fetch(4, envelope([source_row(4)])).items[0]
    assert [week.week_index for week in row.weeks] == list(range(1, 14))
    assert all(week.forecast_qty == Decimal(0) and week.week_start_date is None for week in row.weeks)
    assert row.thirteen_week_demand_qty == row.weekly_average_demand_qty == 0
    assert row.advance_shipping_notice_qty is None and row.weekly_forecast_snapshot_id is None


def test_week_order_is_preserved_and_missing_slot_fails():
    source = source_row(4) | {f"week_{i:02d}_forecast_qty": str(i) for i in range(1, 14)}
    row = fetch(4, envelope([source])).items[0]
    assert [week.forecast_qty for week in row.weeks] == [Decimal(i) for i in range(1, 14)]
    # Totals are source facts, not recomputed by the structural adapter.
    assert row.thirteen_week_demand_qty == 0
    source.pop("week_13_forecast_qty")
    with pytest.raises(SystemAResponseValidationError):
        fetch(4, envelope([source]))


def test_two_shipments_are_not_collapsed_to_one_po_line():
    rows = [source_row(1), source_row(1) | {"shipment_number": 4}]
    result = fetch(1, envelope(rows))
    assert [row.shipment_number for row in result.items] == [3, 4]
    assert all(row.po_line_number == 2 for row in result.items)


@pytest.mark.parametrize("field,value", [
    ("future_months", [{"period": "2026-09-01", "quantity": "bad"}]),
    ("inventory_age_quantities", [{"threshold_days": 30, "quantity": None}]),
])
def test_nested_stockpile_response_validation(field, value):
    with pytest.raises(SystemAResponseValidationError):
        fetch(6, envelope([source_row(6) | {field: value}]))


def test_product_lifecycle_and_timezone_are_source_facts():
    row = fetch(5, envelope([source_row(5)])).items[0]
    assert row.lifecycle_stage == "EOL"
    assert row.modified_at.utcoffset().total_seconds() == 8 * 3600
    assert "mpm" not in type(row).model_fields and row.project_id is None
    with pytest.raises(SystemAResponseValidationError):
        fetch(5, envelope([source_row(5) | {"lifecycle_stage": "AFTER_SALES"}]))


def test_stockpile_zero_target_nested_types_and_missing_actual():
    row = fetch(6, envelope([source_row(6)])).items[0]
    assert row.target_stockpile_qty == 0 and row.stockpile_completion_ratio is None
    assert row.actual_stockpile_qty is None and row.currency is None
    assert row.agreement_unit_price == Decimal("1.2345")
    assert row.future_months[-1].period == date(2027, 2, 1)
    assert row.inventory_age_quantities[1].quantity == Decimal(2)
    assert row.stockpile_version_date == date(2026, 8, 25) != row.snapshot_date
    over_target = fetch(6, envelope([source_row(6) | {"stockpile_completion_ratio": "1.25"}])).items[0]
    assert over_target.stockpile_completion_ratio == Decimal("1.25")


@pytest.mark.parametrize("overrides", [
    {"dataset_version_id": str(OTHER_DID)}, {"page": 2}, {"page_size": 99},
    {"total": -1}, {"total": 2}, {"total": 0}, {"snapshot_date": "not-date"},
])
def test_inconsistent_pagination_or_context(overrides):
    with pytest.raises(SystemAResponseValidationError):
        fetch(1, envelope([source_row(1)], **overrides))


@pytest.mark.parametrize("report_id", [1, 4])
def test_row_snapshot_must_equal_envelope(report_id):
    with pytest.raises(SystemAResponseValidationError):
        fetch(report_id, envelope([source_row(report_id) | {"snapshot_date": "2026-08-25"}]))


@pytest.mark.parametrize("mutation", [None, "snapshot_date", "total", "dataset_version_id"])
def test_iteration_completeness_and_cross_page_consistency(mutation):
    requested = []

    def handler(request):
        number = int(request.url.params["page"])
        requested.append(number)
        payload = envelope([source_row(3)], page=number, page_size=1, total=2)
        if number == 2 and mutation:
            payload[mutation] = {"snapshot_date": "2026-08-25", "total": 3,
                                 "dataset_version_id": str(OTHER_DID)}[mutation]
        return httpx.Response(200, json=payload)

    with adapter_for(handler) as adapter:
        iterator = adapter.iter_pages(adapter.forecast_history, DID, page_size=1)
        if mutation:
            assert next(iterator).page == 1
            with pytest.raises(SystemAResponseValidationError):
                next(iterator)
        else:
            assert [batch.page for batch in iterator] == [1, 2]
    assert requested == [1, 2]


def test_out_of_range_page_is_valid_empty_and_empty_iterator_stops():
    with adapter_for(lambda request: httpx.Response(200, json=envelope([], page=3, total=1))) as adapter:
        result = adapter.purchase_orders(DID, page=3)
        assert result.items == () and result.total == 1
    with adapter_for(lambda request: httpx.Response(200, json=envelope([]))) as adapter:
        assert len(list(adapter.iter_pages(adapter.purchase_orders, DID))) == 1


@pytest.mark.parametrize("report_id,method,path,model", REPORTS)
def test_unknown_answers_and_unexposed_ids_do_not_cross_boundary(report_id, method, path, model):
    row = source_row(report_id) | {"cause_type": "TRIAL", "expected_action": "private",
                                  "causal_project_id": str(OTHER_DID), "material_id": str(OTHER_DID)}
    result = fetch(report_id, envelope([row])).items[0]
    assert result.material_id is None
    assert not {"cause_type", "expected_action", "causal_project_id"}.intersection(result.model_dump())


def dataset_payload(status="READY"):
    return {"dataset_version_id": str(DID), "dataset_version_name": "synthetic-test",
            "snapshot_date": SNAPSHOT, "status": status, "generation_signature": "signature",
            "business_content_hash": None}


@pytest.mark.parametrize("status", ["GENERATING", "READY", "FAILED", "RETIRED"])
def test_dataset_metadata_does_not_silently_filter_status(status):
    def handler(request):
        row = dataset_payload(status)
        return httpx.Response(200, json={"items": [row], "total": 1} if request.url.path.endswith("datasets") else row)

    with adapter_for(handler) as adapter:
        assert adapter.list_datasets()[0].status == status
        assert adapter.get_dataset(DID).business_content_hash is None


def test_dataset_metadata_mismatch_fails():
    with adapter_for(lambda request: httpx.Response(200, json=dataset_payload())) as adapter:
        with pytest.raises(SystemAResponseValidationError):
            adapter.get_dataset(OTHER_DID)
    with adapter_for(lambda request: httpx.Response(200, json={"items": [], "total": 1})) as adapter:
        with pytest.raises(SystemAResponseValidationError):
            adapter.list_datasets()


@pytest.mark.parametrize("kwargs", [{"page": 0}, {"page_size": 501}, {"page_size": True}])
def test_invalid_local_pagination_does_not_make_http_request(kwargs):
    with adapter_for(lambda request: pytest.fail("HTTP must not be called")) as adapter:
        with pytest.raises(ValueError):
            adapter.purchase_orders(DID, **kwargs)


def test_uuid_required_and_no_unimplemented_filter_forwarding():
    with adapter_for(lambda request: pytest.fail("HTTP must not be called")) as adapter:
        with pytest.raises(TypeError):
            adapter.purchase_orders(str(DID))
        with pytest.raises(TypeError):
            adapter.stockpile(DID, as_of_date=date(2025, 1, 1))


@pytest.mark.parametrize("url", ["ftp://invalid.test", "https://user:pass@invalid.test", "https://invalid.test/?token=x"])
def test_invalid_base_url_rejected(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, system_a_base_url=url)


def test_settings_env_and_required_configuration(monkeypatch):
    monkeypatch.setenv("SYSTEM_A_BASE_URL", "https://enterprise.invalid/api/v1")
    monkeypatch.setenv("SYSTEM_A_TIMEOUT_SECONDS", "4.5")
    configured = Settings(_env_file=None)
    assert str(configured.system_a_base_url) == "https://enterprise.invalid/api/v1"
    assert configured.system_a_timeout_seconds == 4.5
    with pytest.raises(ValueError, match="SYSTEM_A_BASE_URL"):
        SystemAAdapter(Settings(_env_file=None, system_a_base_url=None))
    with pytest.raises(ValidationError):
        Settings(_env_file=None, system_a_timeout_seconds=0)


def test_context_manager_closes_owned_transport():
    class TrackedTransport(httpx.MockTransport):
        closed = False

        def close(self):
            self.closed = True

    transport = TrackedTransport(lambda request: httpx.Response(200, json=envelope([])))
    with SystemAAdapter(Settings(_env_file=None, system_a_base_url="https://enterprise.invalid"),
                        transport=transport) as adapter:
        adapter.purchase_orders(DID)
    assert transport.closed


@pytest.mark.parametrize("report_id,method,path,model", REPORTS)
def test_actual_fastapi_route_and_source_schema_compatibility(monkeypatch, report_id, method, path, model):
    """Exercise real routing/projection/serialization with a substituted query boundary."""
    from app.api import reports
    from app.db.session import get_db_session
    from app.main import create_app
    from app.services.report_queries import ReportQueryService, SelectedDataset

    class StubQueryService:
        def __init__(self, session):
            pass

        def select_dataset(self, dataset_version_id, dataset_version_name):
            assert dataset_version_id == DID and dataset_version_name is None
            return SelectedDataset(DID, "test", date(2026, 8, 26), "GENERATING", "signature", None)

        def page(self, requested_id, dataset, page, page_size, filters):
            assert requested_id == report_id and filters["material_code"] == "MAT-TEST-001"
            row = ReportQueryService._public_row(report_id, source_row(report_id))
            if report_id == 6:
                row.update({key: source_row(6)[key] for key in ("future_months", "inventory_age_quantities")})
            return 1, [row]

        def report6_page(self, dataset, page, page_size, filters):
            return self.page(6, dataset, page, page_size, filters)

    monkeypatch.setattr(reports, "ReportQueryService", StubQueryService)
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: None
    with TestClient(application) as client:
        def handler(request):
            relative = request.url.path.replace("/custom", "", 1)
            response = client.get(relative, params=dict(request.url.params))
            assert response.status_code == 200
            return httpx.Response(response.status_code, content=response.content)

        with adapter_for(handler) as adapter:
            result = getattr(adapter, method)(DID, material_code="MAT-TEST-001")
        assert isinstance(result.items[0], model)


def test_system_b_import_boundary_and_canonical_schema():
    root = Path(__file__).resolve().parents[1] / "app" / "system_b"
    prohibited = ("app.models", "app.db", "app.reporting", "app.services", "app.generators", "app.schemas", "sqlalchemy")
    for source in root.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports = [node.module or ""] if isinstance(node, ast.ImportFrom) else (
                [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            )
            assert not any(name.startswith(prohibited) for name in imports), source.name
    for _, _, _, model in REPORTS:
        fields = model.model_fields
        assert not {"cause_type", "causal_project_id", "expected_action", "demand_change_type"}.intersection(fields)
    item = fetch(1, envelope([source_row(1)])).items[0]
    with pytest.raises(ValidationError):
        item.material_code = "changed"
