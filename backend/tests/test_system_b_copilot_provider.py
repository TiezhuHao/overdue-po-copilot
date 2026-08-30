"""Exercise the installed official SDK through an in-memory HTTP transport."""
import json
import logging
import os

import httpx2
import pytest

from app.system_b.copilot.models import Intent, IntentDraft
from app.system_b.copilot.provider import OpenAILLM, LLMFailure
from app.system_b.copilot.settings import CopilotSettings
from app.system_b.copilot.grounding import project_execution, fallback_draft
from app.system_b.agent.graph import ProcurementAgent
from tests.test_system_b_agent_tools import CanonicalAdapter, request


def settings(**overrides):
    return CopilotSettings(openai_api_key="fixture-only-not-a-key", openai_model="fixture-configured-model", **overrides)


def response_body(text, **overrides):
    return dict(id="resp_fixture", object="response", created_at=1, status="completed", model="fixture-configured-model",
        output=[dict(id="msg_fixture", type="message", role="assistant", status="completed",
                     content=[dict(type="output_text", text=text, annotations=[])])]) | overrides


def test_official_responses_strict_schema_store_false_and_configured_model():
    seen = []
    parsed = IntentDraft(intent=Intent.EXPLAIN_DIAGNOSIS, po_number="PO-TEST", material_code=None)
    def handler(request):
        seen.append(json.loads(request.content))
        assert str(request.url) == "https://api.openai.com/v1/responses" and request.method == "POST"
        return httpx2.Response(200, json=response_body(parsed.model_dump_json()))
    client = OpenAILLM(settings(), transport=httpx2.MockTransport(handler))
    try:
        assert client.parse_intent("为什么 PO-TEST 超期？") == parsed
    finally:
        client.close()
    body = seen[0]
    assert len(seen) == 1 and body["store"] is False and body["model"] == "fixture-configured-model"
    assert body["temperature"] == 0 and body["max_output_tokens"] == 4000
    schema = body["text"]["format"]
    assert schema["strict"] is True and schema["type"] == "json_schema"
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == {"intent", "po_number", "material_code"}
    assert "tools" not in body and "policy" not in schema["schema"]["properties"]
    assert [item["role"] for item in body["input"]] == ["system", "user"]
    assert "fixture-only-not-a-key" not in json.dumps(body)


def test_composition_sdk_receives_only_projected_result_and_all_required_schema():
    packet = project_execution(ProcurementAgent(CanonicalAdapter()).execute(request()))
    expected = fallback_draft(packet)
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=response_body(expected.model_dump_json()))
    client = OpenAILLM(settings(openai_temperature=None), transport=httpx2.MockTransport(handler))
    try:
        assert client.compose(packet, Intent.ANALYZE_OVERDUE_PO) == expected
    finally:
        client.close()
    assert "temperature" not in seen[0]
    model_input = json.loads(seen[0]["input"][1]["content"])
    assert set(model_input) == {"intent", "grounding"}
    assert "policy_fingerprint" not in json.dumps(model_input) and "user_query" not in json.dumps(model_input)
    schema = seen[0]["text"]["format"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.parametrize("mode,code", [("timeout", "LLM_TIMEOUT"), ("connection", "LLM_UNAVAILABLE"),
    ("auth", "LLM_REJECTED_REQUEST"), ("rate_limit", "LLM_REJECTED_REQUEST"),
    ("malformed", "LLM_INVALID_RESPONSE"), ("invalid_schema", "LLM_INVALID_RESPONSE"),
    ("incomplete", "LLM_INVALID_RESPONSE"), ("refusal", "LLM_INVALID_RESPONSE")])
def test_provider_errors_are_bounded_and_redacted(mode, code, caplog):
    attempts = []
    def handler(request):
        attempts.append(True)
        if mode == "timeout":
            raise httpx2.ReadTimeout("private provider body")
        if mode == "connection":
            raise httpx2.ConnectError("private provider body")
        if mode in ("auth", "rate_limit"):
            return httpx2.Response(401 if mode == "auth" else 429, json={"error": {"message": "private provider body"}})
        body = response_body("invalid json" if mode == "malformed" else '{"intent":"CANCEL"}')
        if mode == "incomplete":
            body.update(status="incomplete", output=[], incomplete_details={"reason": "max_output_tokens"})
        if mode == "refusal":
            body["output"][0]["content"] = [{"type": "refusal", "refusal": "private provider refusal"}]
        return httpx2.Response(200, json=body)
    client = OpenAILLM(settings(), transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises(LLMFailure) as caught:
            client.parse_intent("测试")
    finally:
        client.close()
    assert caught.value.code == code and len(attempts) == 1
    assert "private" not in str(caught.value) and "private" not in caplog.text


def test_missing_configuration_never_contacts_network(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = OpenAILLM(CopilotSettings(), transport=httpx2.MockTransport(lambda request: pytest.fail("network called")))
    with pytest.raises(LLMFailure, match="LLM_NOT_CONFIGURED"):
        client.parse_intent("分析 PO")
    client.close()


def test_environment_secret_hidden_and_model_parameters_configurable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=ignored-file-value\nOPENAI_MODEL=ignored-model\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert CopilotSettings().openai_api_key is None and CopilotSettings().openai_model is None
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-server-value")
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "null")
    configured = CopilotSettings()
    assert configured.openai_model == "configured-model" and configured.openai_temperature is None
    assert "fixture-server-value" not in repr(configured) + configured.model_dump_json()


def test_sdk_debug_logging_does_not_emit_prompt_or_key(caplog):
    caplog.set_level(logging.DEBUG)
    parsed = IntentDraft(intent=Intent.UNSUPPORTED, po_number=None, material_code=None)
    client = OpenAILLM(settings(), transport=httpx2.MockTransport(
        lambda request: httpx2.Response(200, json=response_body(parsed.model_dump_json()))))
    try:
        client.parse_intent("private-query-sentinel")
    finally:
        client.close()
    assert "private-query-sentinel" not in caplog.text and "fixture-only-not-a-key" not in caplog.text


@pytest.mark.llm_integration
def test_live_openai_structured_intent_smoke():
    # Collection additionally requires --run-llm-integration. No procurement records sent.
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        pytest.skip("OPENAI_API_KEY and OPENAI_MODEL are required for the opt-in smoke test")
    client = OpenAILLM(CopilotSettings())
    try:
        result = client.parse_intent("帮我分析 PO SMOKE-ONLY。")
        assert isinstance(result, IntentDraft)
    finally:
        client.close()
