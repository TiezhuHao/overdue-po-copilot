import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db_session
from app.main import app
from tests.test_operational_integration import operational_worlds
from tests.test_forecast_integration import forecast_worlds


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api_world(operational_worlds):
    return operational_worlds[0]


@pytest.fixture()
def client(migrated_database):
    def override():
        with Session(migrated_database) as session:
            yield session
    app.dependency_overrides[get_db_session] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_and_get_datasets(client, api_world):
    listed = client.get("/api/v1/datasets")
    assert listed.status_code == 200 and listed.json()["total"] >= 1
    item = client.get(f"/api/v1/datasets/{api_world.dataset_version_id}")
    assert item.status_code == 200
    assert item.json()["status"] == "GENERATING"
    assert set(item.json()) == {"dataset_version_id", "dataset_version_name", "snapshot_date", "status", "generation_signature", "business_content_hash"}


def test_default_requires_ready_dataset(client):
    response = client.get("/api/v1/reports/overdue-pos")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "NO_READY_DATASET"


@pytest.mark.parametrize("path", [
    "overdue-pos", "material-supply-demand", "forecast-history",
    "latest-13w-forecast", "product-configurations", "stockpile",
])
def test_six_report_endpoints_explicit_generating(client, api_world, path):
    response = client.get(f"/api/v1/reports/{path}", params={"dataset_version_id": str(api_world.dataset_version_id), "page_size": 5})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dataset_version_id"] == str(api_world.dataset_version_id)
    assert payload["page"] == 1 and payload["page_size"] == 5 and payload["total"] > 0
    assert 0 < len(payload["items"]) <= 5


def test_report3_pagination_and_stable_ordering(client, api_world):
    params = {"dataset_version_id": str(api_world.dataset_version_id), "page_size": 7, "page": 2}
    first = client.get("/api/v1/reports/forecast-history", params=params)
    second = client.get("/api/v1/reports/forecast-history", params=params)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    assert len(first.json()["items"]) == 7


def test_report_filters(client, api_world):
    base = {"dataset_version_id": str(api_world.dataset_version_id), "page_size": 1}
    item1 = client.get("/api/v1/reports/overdue-pos", params=base).json()["items"][0]
    filtered1 = client.get("/api/v1/reports/overdue-pos", params={**base, "po_number": item1["po_number"]})
    assert filtered1.status_code == 200 and all(row["po_number"] == item1["po_number"] for row in filtered1.json()["items"])
    item2 = client.get("/api/v1/reports/material-supply-demand", params=base).json()["items"][0]
    filtered2 = client.get("/api/v1/reports/material-supply-demand", params={**base, "material_code": item2["material_code"]})
    assert filtered2.status_code == 200 and filtered2.json()["total"] == 1


def test_openapi_has_six_reports_and_no_private_terms(client):
    document = client.get("/openapi.json").json()
    paths = document["paths"]
    assert sum(path.startswith("/api/v1/reports/") for path in paths) == 6
    rendered = json.dumps(document).lower()
    assert all(term not in rendered for term in ("true_cause", "scenario_pattern", "causal_project_id", "expected_action", "evaluation"))


@pytest.mark.parametrize("path", [
    "overdue-pos", "material-supply-demand", "forecast-history",
    "latest-13w-forecast", "product-configurations", "stockpile",
])
def test_report_http_with_real_api_role(client, api_world, test_database_url, path):
    params = {"dataset_version_id": str(api_world.dataset_version_id), "page_size": 2}
    expected = client.get(f"/api/v1/reports/{path}", params=params)
    assert expected.status_code == 200
    credentials = make_url(settings.database_url_api.get_secret_value())
    api_url = make_url(test_database_url).set(
        username=credentials.username, password=credentials.password,
    )
    engine = create_engine(api_url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == "system_a_api"
            connection.rollback()
            for source in ("platform.materials", "evaluation.scenario_truth"):
                with pytest.raises(DBAPIError) as denied:
                    connection.execute(text(f"SELECT 1 FROM {source} LIMIT 1"))
                assert denied.value.orig.sqlstate == "42501"
                connection.rollback()

        def api_session():
            with Session(engine) as session:
                yield session

        previous = app.dependency_overrides[get_db_session]
        app.dependency_overrides[get_db_session] = api_session
        try:
            response = TestClient(app, raise_server_exceptions=False).get(
                f"/api/v1/reports/{path}", params=params,
            )
        finally:
            app.dependency_overrides[get_db_session] = previous
        assert response.status_code == 200, f"{path}: HTTP {response.status_code}"
        assert response.json() == expected.json()
        if path == "stockpile":
            assert all(len(row["future_months"]) == 6 for row in response.json()["items"])
            assert all(row["inventory_age_quantities"] for row in response.json()["items"])
    finally:
        engine.dispose()
