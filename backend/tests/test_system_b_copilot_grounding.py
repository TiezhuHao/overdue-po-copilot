"""Reject changed structured claims and unsupported prose, even with valid JSON."""
import ast
from pathlib import Path

import pytest

from app.system_b.agent.graph import ProcurementAgent
from app.system_b.copilot.grounding import project_execution, fallback_draft, validate_draft, GroundingError
from app.system_b.copilot.models import CopilotAnswerDraft
from tests.test_system_b_agent_tools import CanonicalAdapter, request
from tests.test_system_b_diagnosis_completion import facts
from tests.test_system_b_diagnosis import po
from tests.test_system_b_copilot import FakeLLM, ResolverAdapter, query, service


@pytest.fixture(scope="module")
def packet():
    inputs = facts(lifecycle="MASS_PRODUCTION")
    result = ProcurementAgent(CanonicalAdapter(inputs)).execute(request(inputs))
    return project_execution(result)


def tamper(data, field):
    if field == "reason":
        data["primary_reason"] = "AFTER_SALES"
    elif field == "owner":
        data["owner_role"] = "CUSTOMER"
    elif field == "action":
        data["action_codes"] = ["CANCEL_ORDER"]
    elif field == "number":
        data["metrics"][0]["value"] = "999"
    elif field == "unit":
        data["metrics"][0]["unit"] = "月"
    elif field == "availability":
        data["metrics"][0]["availability"] = "NOT_COMPUTABLE"
    elif field == "project_id":
        data["projects"][0]["project_id"] = "00000000-0000-0000-0000-000000000999"
    elif field == "project_display":
        data["projects"][0]["display_value"] = "猜测的责任项目"
    elif field == "duplicate_metric":
        data["metrics"].append(data["metrics"][0])
    elif field == "prose":
        data["sections"][0]["lines"][0]["text"] += "客户应该承担所有责任。"
    elif field == "reference":
        data["sections"][0]["lines"][0]["evidence_reference_ids"] = ["invented"]
    elif field == "unknown_fact":
        data["sections"][0]["lines"][0]["fact_id"] = "invented"
    elif field == "omission":
        data["sections"][-1]["lines"].pop()
    elif field == "duplicate_fact":
        data["sections"][0]["lines"].append(data["sections"][0]["lines"][0])
    elif field == "duplicate_section":
        data["sections"].append(data["sections"][0])
    elif field == "wrong_section":
        data["sections"][0]["lines"].append(data["sections"][1]["lines"].pop())


@pytest.mark.parametrize("field", ["reason", "owner", "action", "number", "unit", "availability", "project_id",
    "project_display", "duplicate_metric", "prose", "reference", "unknown_fact", "omission",
    "duplicate_fact", "duplicate_section", "wrong_section"])
def test_reject_hallucinated_claims_missing_limitations_and_fake_citations(packet, field):
    data = fallback_draft(packet).model_dump()
    tamper(data, field)
    draft = CopilotAnswerDraft.model_validate(data)
    with pytest.raises(GroundingError):
        validate_draft(packet, draft)


def test_prose_hallucination_also_triggers_service_fallback():
    result = service(llm=FakeLLM(mutate=lambda data: tamper(data, "prose"))).query(query())
    assert result.answer_source == "FALLBACK" and "GROUNDING_REJECTED" in result.limitations
    assert "客户应该承担所有责任" not in result.answer


def test_fallback_and_alternative_wording_both_validate_and_refs_resolve(packet):
    assert validate_draft(packet, fallback_draft(packet)) == fallback_draft(packet)
    refs = {item.reference_id for item in packet.evidence_references}
    assert all(set(fact.evidence_reference_ids) <= refs for fact in packet.facts)
    assert any(ref.source == "R3" and ref.version_id and ref.version_date for ref in packet.evidence_references)
    assert all(project.display_value is None for project in packet.projects)
    payload = packet.model_dump_json()
    for forbidden in ("policy_fingerprint", "execution_trace", "business_policy", "source_diagnosis", "forecast_history"):
        assert forbidden not in payload


def test_unknown_numeric_metrics_remain_null_and_no_infinity():
    inputs = facts(po=po(inventory_organization_type="TRIAL"), weekly=None, products=(), forecast_history=None)
    result = service(ResolverAdapter(inputs)).query(query(inputs))
    metrics = {metric.name: metric for metric in result.key_metrics}
    assert metrics["estimated_consumption_weeks"].value is None
    assert metrics["estimated_consumption_weeks"].availability == "NOT_COMPUTABLE"
    assert "不可计算" in result.answer and "Infinity" not in result.answer


def test_model_and_http_imports_do_not_enter_business_engines():
    root = Path(__file__).resolve().parents[1] / "app" / "system_b"
    for folder in ("analytics", "diagnosis", "decision", "agent"):
        for path in (root / folder).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            assert not any(name.startswith(("openai", "app.system_b.copilot")) for name in imports)
