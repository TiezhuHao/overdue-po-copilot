"""Real LangGraph, fixed evidence and no sockets or model providers."""
import ast
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
from decimal import Inexact, ROUND_UP, localcontext
from pathlib import Path

import pytest

from app.system_b.agent.graph import ProcurementAgent, _build_graph
from app.system_b.agent.tools import AgentTools
from app.system_b.agent.models import AgentRequest
from app.system_b.adapters.errors import SystemAUnavailableError
from tests.test_system_b_agent_tools import CanonicalAdapter, request
from tests.test_system_b_diagnosis_completion import facts, GOLDEN
from tests.test_system_b_decision import EXPECTED
from tests.test_system_b_diagnosis import po


@pytest.mark.parametrize("name,values,reason,rule", GOLDEN, ids=[row[0] for row in GOLDEN])
def test_graph_golden_execution(name, values, reason, rule):
    inputs = facts(**values)
    result = ProcurementAgent(CanonicalAdapter(inputs)).execute(request(inputs))
    assert result.diagnosis is not None, result.model_dump_json()
    assert result.diagnosis.primary_reason == reason and result.diagnosis.primary_rule_id == rule
    code, owner = EXPECTED[name]
    assert result.decision.owner_role == owner
    assert result.status == ("COMPLETED" if code else "UNRESOLVED")
    assert [action.action_code for action in result.decision.actions] == ([code] if code else [])
    assert [item.node for item in result.execution_trace] == ["validate_request", "load_context", "analytics",
                                                           "diagnosis", "decision", "structured_result"]
    assert result.decision.source_diagnosis_ref == result.diagnosis.trace_ref == result.provenance.diagnosis_ref
    assert result.decision.trace_ref == result.provenance.decision_ref


def test_same_primary_different_path_is_preserved():
    customer = ProcurementAgent(CanonicalAdapter(facts("reduction"))).execute(request())
    internal = ProcurementAgent(CanonicalAdapter(facts(lifecycle="MASS_PRODUCTION", tag="OTHER"))).execute(request())
    assert customer.diagnosis.primary_reason == internal.diagnosis.primary_reason
    assert customer.decision.decision_rule_id != internal.decision.decision_rule_id
    assert customer.decision.actions[0].action_code != internal.decision.actions[0].action_code


def test_unresolved_diagnosis_still_calls_decision_without_inventing_action():
    result = ProcurementAgent(CanonicalAdapter(facts(weekly=None))).execute(request())
    assert result.status == "UNRESOLVED" and result.diagnosis.status == "UNRESOLVED"
    assert result.decision.decision_status == "NOT_EVALUABLE" and not result.decision.actions
    assert {issue.code for issue in result.issues} == {"BUSINESS_UNRESOLVED", "EVIDENCE_INCOMPLETE"}


def test_partial_analytics_does_not_block_trial():
    inputs = facts(po=po(inventory_organization_type="TRIAL"), weekly=None, products=(), forecast_history=None)
    result = ProcurementAgent(CanonicalAdapter(inputs)).execute(request(inputs, diagnosis_policy=None, decision_policy=None))
    assert result.status == "COMPLETED" and result.diagnosis.primary_reason == "TRIAL"
    assert result.analytics.metrics.consumption.status == "NOT_COMPUTABLE"
    assert result.decision.actions[0].action_code == "REQUEST_MPM_CONFIRMATION"


def test_not_found_ends_before_analytics_and_diagnosis():
    adapter = CanonicalAdapter()
    adapter.empty_po = True
    result = ProcurementAgent(adapter).execute(request())
    assert result.status == "FAILED" and result.issues[0].code == "ENTITY_NOT_FOUND"
    assert result.analytics is result.diagnosis is result.decision is None
    assert [item.node for item in result.execution_trace] == ["validate_request", "load_context", "structured_result"]
    assert len(adapter.calls) == 1


def test_not_eligible_flows_to_not_applicable_decision():
    inputs = facts(po=po(material_lt_days=1000, inventory_organization_type="TRIAL"), stockpile=None, forecast_history=None)
    result = ProcurementAgent(CanonicalAdapter(inputs)).execute(request(inputs))
    assert result.status == "NOT_APPLICABLE" and result.diagnosis.status == "NOT_ELIGIBLE"
    assert result.decision.decision_status == "NOT_APPLICABLE" and not result.decision.actions


@pytest.mark.parametrize("path", ["overdue-pos", "forecast-history", "stockpile"])
def test_upstream_failure_stops_graph_and_never_becomes_empty_evidence(path):
    adapter = CanonicalAdapter(error=SystemAUnavailableError("sensitive-upstream-body"), fail_path=path)
    result = ProcurementAgent(adapter).execute(request())
    assert result.status == "FAILED" and result.issues[0].code == "UPSTREAM_UNAVAILABLE"
    assert result.diagnosis is result.decision is None
    assert "sensitive-upstream-body" not in result.model_dump_json()


def test_invalid_request_never_calls_adapter():
    adapter = CanonicalAdapter()
    result = ProcurementAgent(adapter).execute(request().model_copy(update={"operation": "CANCEL_PO"}))
    assert result.status == "FAILED" and result.request is None and not adapter.calls
    assert result.issues[0].code == "INVALID_REQUEST"


def test_snapshot_mismatch_is_not_silently_resolved():
    from datetime import date
    adapter = CanonicalAdapter()
    adapter.snapshot_override = date(2026, 8, 27)
    result = ProcurementAgent(adapter).execute(request())
    assert result.status == "FAILED" and result.issues[0].code == "UPSTREAM_INVALID_RESPONSE"


def test_later_page_failure_does_not_publish_partial_context():
    class FailingPageAdapter(CanonicalAdapter):
        def _page(self, path, source_type, canonical_type, mapper, did, page, size, filters):
            if path == "forecast-history" and page == 2:
                raise SystemAUnavailableError("partial collection")
            return super()._page(path, source_type, canonical_type, mapper, did, page, size, filters)

    result = ProcurementAgent(FailingPageAdapter(page_limit=7)).execute(request())
    assert result.status == "FAILED" and result.resolved_identity is None
    assert result.analytics is result.diagnosis is result.decision is None
    assert result.provenance.context_ref is None


def test_internal_diagnosis_tool_failure_stops_before_decision(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("sensitive exception payload")

    monkeypatch.setattr("app.system_b.agent.tools.diagnose_business", broken)
    result = ProcurementAgent(CanonicalAdapter()).execute(request())
    assert result.status == "FAILED" and result.analytics is not None and result.decision is None
    assert result.issues[0].code == "INTERNAL_TOOL_FAILURE"
    assert "decision" not in [entry.node for entry in result.execution_trace]
    assert "sensitive exception payload" not in result.model_dump_json()


def test_trace_fact_catalog_has_no_duplicate_payloads_or_dangling_refs():
    result = ProcurementAgent(CanonicalAdapter(facts(lifecycle="MASS_PRODUCTION"))).execute(request())
    catalog = {fact.evidence_id: fact for fact in result.provenance.facts}
    assert len(catalog) == len(result.provenance.facts)
    assert all(set(fact.derived_from) <= catalog.keys() for fact in catalog.values())
    assert all(set(action.evidence_refs) <= catalog.keys() for action in result.decision.actions)
    payload = result.model_dump()
    assert "evidence_trace" not in payload["diagnosis"] and "source_diagnosis" not in payload["decision"]
    assert "inputs" not in payload and "answer" not in payload


def test_determinism_and_no_network_even_when_tracing_env_enabled(monkeypatch):
    import socket
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    agent = ProcurementAgent(CanonicalAdapter(facts(lifecycle="MASS_PRODUCTION")))
    first = agent.execute(request())
    assert first.status == "COMPLETED"
    with localcontext() as ambient:
        ambient.prec, ambient.rounding = 5, ROUND_UP
        ambient.traps[Inexact] = True
        second = agent.execute(request())
        assert ambient.prec == 5 and ambient.rounding == ROUND_UP
    assert first == second
    assert attempts == []


def test_no_persistent_checkpointer_and_independent_concurrent_executions():
    graph = _build_graph(AgentTools(CanonicalAdapter()))
    assert graph.checkpointer is None
    inputs = [facts("reduction"), facts(lifecycle="MASS_PRODUCTION", tag="OTHER")]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda data: ProcurementAgent(CanonicalAdapter(data)).execute(request(data)), inputs))
    assert [result.decision.owner_role for result in results] == ["CUSTOMER", "BUSINESS_UNIT"]
    agent = ProcurementAgent(CanonicalAdapter(facts("reduction")))
    requests = [request(request_id=UUID(int=index)) for index in (801, 802)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(agent.execute, requests))
    assert [result.request.request_id for result in results] == [item.request_id for item in requests]
    assert results[0].provenance.context_ref != results[1].provenance.context_ref


def test_agent_does_not_import_business_rules_or_provider_sdk():
    root = Path(__file__).resolve().parents[1] / "app" / "system_b" / "agent"
    banned = ("openai", "anthropic", "google.genai", "sqlalchemy", "app.services", "app.generators",
              "app.system_b.diagnosis.business_rules", "app.system_b.decision.rules")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        modules += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(module.startswith(banned) for module in modules)
