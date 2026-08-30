"""Consumer evidence contracts and projection allowlists, without network or DB."""
from datetime import date, timedelta
import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.report_queries import ReportQueryService
from app.main import app
from app.system_b.adapters.errors import SystemAResponseValidationError
from tests.test_system_b_adapter import DID, OTHER_DID, REPORTS, adapter_for, envelope, fetch, source_row


MID, VID, PID = UUID(int=11), UUID(int=12), UUID(int=13)


def weekly_row():
    row = source_row(4)
    row.update(material_id=str(MID), organization_id=str(UUID(int=14)),
               weekly_forecast_snapshot_id=str(UUID(int=15)), source_forecast_version_id=str(VID),
               forecast_snapshot_date="2026-08-26")
    row["weeks"] = [{"week_index": i, "week_start_date": (date(2026, 8, 31) + timedelta(weeks=i-1)).isoformat(),
                     "forecast_qty": row[f"week_{i:02d}_forecast_qty"]} for i in range(1, 14)]
    row["project_contributions"] = [week | {"project_id": str(PID)} for week in row["weeks"]]
    return row


def test_weekly_identity_and_dates_are_mapped_without_guessing_or_ranking():
    row = weekly_row()
    row["weeks"].reverse()
    result = fetch(4, envelope([row])).items[0]
    assert result.material_id == MID and result.source_forecast_version_id == VID
    assert result.weeks[0].week_start_date == date(2026, 8, 31)
    assert result.weeks[-1].week_start_date == date(2026, 11, 23)
    assert {item.project_id for item in result.project_contributions} == {PID}


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "date", "quantity", "project_date", "project_duplicate", "future_snapshot"])
def test_inconsistent_week_evidence_is_rejected(corruption):
    row = weekly_row()
    if corruption == "missing":
        row["weeks"].pop()
    elif corruption == "duplicate":
        row["weeks"][-1] = row["weeks"][0]
    elif corruption == "date":
        row["weeks"][0]["week_start_date"] = "2026-09-01"
    elif corruption == "quantity":
        row["weeks"][0]["forecast_qty"] = "12345"
    elif corruption == "project_date":
        row["project_contributions"][0]["week_start_date"] = "2026-09-07"
    elif corruption == "project_duplicate":
        row["project_contributions"].append(row["project_contributions"][0])
    else:
        row["forecast_snapshot_date"] = "2026-08-27"
    with pytest.raises(SystemAResponseValidationError):
        fetch(4, envelope([row]))


@pytest.mark.parametrize("report_id,method,path,model", REPORTS)
def test_public_projection_keeps_only_approved_evidence(report_id, method, path, model):
    private = {key: "private" for key in (
        "diagnosis_reason", "root_cause", "recommended_action", "responsible_project",
        "should_cancel", "should_reschedule", "causal_project_id", "demand_signal_id",
    )}
    row = source_row(report_id) | {"material_id": MID} | private
    public = ReportQueryService._public_row(report_id, row)
    assert public["material_id"] == MID and not private.keys() & public.keys()


def test_stable_filter_forwarding_and_ignored_filter_rejection():
    def handler(request):
        assert request.url.params["material_id"] == str(MID)
        return httpx.Response(200, json=envelope([source_row(1) | {"material_id": str(OTHER_DID)}]))
    with adapter_for(handler) as adapter:
        with pytest.raises(SystemAResponseValidationError):
            adapter.purchase_orders(DID, material_id=MID)


def test_stockpile_selection_preserves_empty_version_vs_empty_material():
    requested = date(2025, 1, 1)
    for version in (None, str(VID)):
        payload = envelope([]) | {"stockpile_selection": {
            "as_of_date": requested.isoformat(), "stockpile_version_id": version,
            "stockpile_version_date": requested.isoformat() if version else None,
            "sequence_no": 2 if version else None,
        }}
        with adapter_for(lambda request: httpx.Response(200, json=payload)) as adapter:
            result = adapter.stockpile(DID, as_of_date=requested, material_id=MID)
        assert result.items == ()
        assert result.stockpile_selection.stockpile_version_id == (VID if version else None)


@pytest.mark.parametrize("corruption", ["missing", "future", "wrong_as_of", "wrong_record_version"])
def test_stockpile_history_cannot_silently_be_current_or_other_version(corruption):
    row = source_row(6) | {"stockpile_version_id": str(VID), "stockpile_version_sequence": 1}
    payload = envelope([row]) | {"stockpile_selection": {
        "as_of_date": "2026-08-26", "stockpile_version_id": str(VID),
        "stockpile_version_date": row["stockpile_version_date"], "sequence_no": 1,
    }}
    if corruption == "missing":
        payload.pop("stockpile_selection")
    elif corruption == "future":
        payload["stockpile_selection"]["stockpile_version_date"] = "2026-08-27"
    elif corruption == "wrong_as_of":
        payload["stockpile_selection"]["as_of_date"] = "2026-08-25"
    else:
        row["stockpile_version_id"] = str(OTHER_DID)
    with adapter_for(lambda request: httpx.Response(200, json=payload)) as adapter:
        with pytest.raises(SystemAResponseValidationError):
            adapter.stockpile(DID, as_of_date=date(2026, 8, 26))


def test_legacy_stockpile_response_still_works_without_historical_request():
    assert fetch(6, envelope([source_row(6)])).stockpile_selection is None


def test_openapi_exposes_facts_not_diagnosis_or_actions():
    schema = TestClient(app).get("/openapi.json").json()
    rendered = json.dumps(schema).lower()
    assert sum(path.startswith("/api/v1/reports/") for path in schema["paths"]) == 6
    assert not any(term in rendered for term in (
        "diagnosis_reason", "root_cause", "recommended_action", "responsible_project",
        "should_cancel", "should_reschedule", "causal_project_id", "scenario_truth",
    ))
