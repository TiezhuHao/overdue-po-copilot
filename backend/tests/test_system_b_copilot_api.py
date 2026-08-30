"""Minimal separate System B API; no live provider or System A dependency."""
import pytest
from fastapi.testclient import TestClient

from app.system_b.copilot.api import create_app, get_copilot_service
from app.system_b.copilot.provider import LLMFailure
from tests.test_system_b_copilot import service, query, FakeLLM


def client_for(supplied=None):
    app = create_app()
    app.dependency_overrides[get_copilot_service] = lambda: supplied or service()
    return TestClient(app)


def test_query_public_projection_contains_no_internal_trace_or_policy():
    with client_for() as client:
        response = client.post("/api/v1/copilot/query", json=query().model_dump(mode="json"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UNRESOLVED" and payload["diagnosis"]["primary_reason"] == "AFTER_SALES"
    assert payload["evidence_references"] and payload["execution_reference"] == payload["request_id"]
    for term in ("execution_trace", "policy_fingerprint", "business_policy", "provenance", "api_key", "user_query"):
        assert term not in response.text


def test_model_outage_is_successful_business_response_with_fallback():
    with client_for(service(llm=FakeLLM(parse_error=LLMFailure("LLM_UNAVAILABLE")))) as client:
        response = client.post("/api/v1/copilot/query", json=query().model_dump(mode="json"))
    assert response.status_code == 200 and response.json()["answer_source"] == "FALLBACK"
    assert response.json()["diagnosis"]["primary_reason"] == "AFTER_SALES"


def test_missing_context_returns_structured_clarification():
    with client_for() as client:
        response = client.post("/api/v1/copilot/query", json={"user_query": "为什么这个 PO 超期？"})
    assert response.status_code == 200 and response.json()["status"] == "NEEDS_CLARIFICATION"
    assert response.json()["limitations"] == ["MISSING_DATASET"]


@pytest.mark.parametrize("updates", [{"api_key": "private-input"}, {"diagnosis_policy": {"private": "input"}},
    {"dataset_version_id": "private-input"}, {"user_query": " "}, {"po_line_number": True}])
def test_invalid_public_input_does_not_echo_values(updates):
    payload = query().model_dump(mode="json") | updates
    with client_for() as client:
        response = client.post("/api/v1/copilot/query", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "INVALID_REQUEST"}}


def test_internal_exception_has_no_stack_trace_or_raw_body():
    class Broken:
        def query(self, request):
            raise RuntimeError("private-stack-trace-or-credential")
    with client_for(Broken()) as client:
        response = client.post("/api/v1/copilot/query", json=query().model_dump(mode="json"))
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "INTERNAL_COPILOT_FAILURE"}}


def test_invalid_server_configuration_sanitized(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "private-invalid-configuration")
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/copilot/query", json=query().model_dump(mode="json"))
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "COPILOT_CONFIGURATION_UNAVAILABLE"}}


def test_only_one_copilot_route_and_system_a_openapi_unchanged():
    from app.main import app as system_a
    assert set(create_app().openapi()["paths"]) == {"/api/v1/copilot/query"}
    assert "/api/v1/copilot/query" not in system_a.openapi()["paths"]
    public_schema = create_app().openapi()["components"]["schemas"]["CopilotRequest"]
    assert public_schema["additionalProperties"] is False
    assert not {"api_key", "openai_api_key", "diagnosis_policy", "decision_policy", "tool_name"} & set(public_schema["properties"])
