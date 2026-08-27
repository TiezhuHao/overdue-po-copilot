from fastapi.testclient import TestClient
import pytest

from app.api.health import get_readiness_checker
from app.main import app
from app.services.readiness import ReadinessError, ReadinessResult


class ReadyChecker:
    def check(self) -> ReadinessResult:
        return ReadinessResult(database="ok", migration="ok")


class FailingChecker:
    def check(self) -> ReadinessResult:
        raise ReadinessError("not ready")


@pytest.mark.parametrize("path", ["/ready", "/api/v1/ready"])
def test_ready(path: str) -> None:
    app.dependency_overrides[get_readiness_checker] = ReadyChecker
    try:
        response = TestClient(app).get(path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "migration": "ok",
    }


@pytest.mark.parametrize("path", ["/ready", "/api/v1/ready"])
def test_ready_returns_503_when_database_is_unavailable(path: str) -> None:
    app.dependency_overrides[get_readiness_checker] = FailingChecker
    try:
        response = TestClient(app).get(path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "not_ready"
