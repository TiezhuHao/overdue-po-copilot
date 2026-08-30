"""Tool isolation with canonical fixtures and the actual Adapter pagination."""
from datetime import date
from uuid import UUID

import httpx
import pytest

from app.system_b.adapters.system_a import SystemAAdapter
from app.system_b.adapters.errors import (
    SystemAUnavailableError, SystemANotFoundError, SystemAHTTPError, SystemAResponseValidationError,
)
from app.system_b.models import CanonicalPage
from app.system_b.agent.models import (
    AgentRequest, ContextRequest, AnalyticsInput, DiagnosisInput, DecisionInput, ToolName,
)
from app.system_b.agent.tools import AgentTools, TOOL_CONTRACTS
from app.system_b.decision.models import CONFIRMED_CONSUMPTION_POLICY
from tests.test_system_b_diagnosis_completion import facts, policy
from tests.test_system_b_diagnosis import po
from tests.test_system_b_adapter import adapter_for, source_row


class CanonicalAdapter(SystemAAdapter):
    """No HTTP client; inherited six methods / iter_pages retain their signatures."""
    def __init__(self, inputs=None, error=None, fail_path="overdue-pos", page_limit=100):
        self.inputs = inputs if inputs is not None else facts()
        self.error, self.fail_path, self.page_limit = error, fail_path, page_limit
        self.calls = []
        self.empty_po = False
        self.snapshot_override = None

    def _page(self, path, source_type, canonical_type, mapper, dataset_version_id, page, page_size, filters):
        filters = {key: value for key, value in filters.items() if value is not None}
        self.calls.append((path, dataset_version_id, page, filters))
        if self.error is not None and path == self.fail_path:
            raise self.error
        inputs = self.inputs
        rows = {"overdue-pos": () if self.empty_po else (inputs.po,),
                "material-supply-demand": (inputs.supply,) if inputs.supply else (),
                "latest-13w-forecast": (inputs.weekly,) if inputs.weekly else (),
                "forecast-history": inputs.forecast_history or (),
                "product-configurations": inputs.products,
                "stockpile": inputs.stockpile.page.items if inputs.stockpile else ()}[path]
        selection = inputs.stockpile.page.stockpile_selection if path == "stockpile" and inputs.stockpile else None
        return CanonicalPage[canonical_type](dataset_version_id=dataset_version_id,
            snapshot_date=self.snapshot_override or inputs.po.snapshot_date, page=page, page_size=page_size,
            total=len(rows), items=rows[(page-1)*page_size:page*page_size], stockpile_selection=selection)

    def iter_pages(self, fetch_page, dataset_version_id, *, page_size=100, **filters):
        return super().iter_pages(fetch_page, dataset_version_id, page_size=min(page_size, self.page_limit), **filters)


def request(inputs=None, **updates):
    inputs = inputs if inputs is not None else facts()
    return AgentRequest(**(dict(request_id=UUID(int=800), dataset_version_id=inputs.po.dataset_version_id,
        snapshot_date=inputs.po.snapshot_date, po_line_schedule_id=inputs.po.po_line_schedule_id,
        diagnosis_policy=policy(), decision_policy=CONFIRMED_CONSUMPTION_POLICY) | updates))


def load(tools, req=None):
    req = req or request()
    return tools.get_overdue_po_context(ContextRequest(**req.model_dump(include=set(ContextRequest.model_fields))))


def prepare(inputs=None):
    adapter = CanonicalAdapter(inputs)
    tools = AgentTools(adapter)
    output = load(tools).output
    arguments = dict(identity=output.identity, context_ref=output.context_ref)
    analytics = tools.get_overdue_po_analytics(AnalyticsInput(**arguments))
    diagnosis = tools.diagnose_overdue_po(DiagnosisInput(**arguments, policy=policy()))
    return tools, arguments, analytics, diagnosis


def test_context_stable_identity_historical_query_and_complete_pagination():
    adapter = CanonicalAdapter(page_limit=7)
    result = load(AgentTools(adapter))
    assert result.status == "SUCCESS" and result.output.identity.material_id == adapter.inputs.po.material_id
    history = [call for call in adapter.calls if call[0] == "forecast-history"]
    assert [call[2] for call in history] == [1, 2, 3]
    assert all(call[3]["po_line_schedule_id"] == adapter.inputs.po.po_line_schedule_id for call in history)
    assert adapter.calls[-1][3] == {"material_id": adapter.inputs.po.material_id, "as_of_date": adapter.inputs.po.order_date}
    assert all(not set(call[3]) & {"po_number", "material_code", "project"} for call in adapter.calls)


def test_all_tools_return_existing_engine_results_and_trace_refs():
    tools, args, analytics, diagnosis = prepare(facts("reduction", lifecycle="NPI"))
    assert analytics.status == "SUCCESS" and analytics.output.metrics.aging.threshold_delta_days > 0
    assert diagnosis.output.primary_reason == "DEMAND_ADJUSTMENT"
    result = tools.get_procurement_decision(DecisionInput(**args, diagnosis_ref=diagnosis.output.trace_ref,
                                                         policy=CONFIRMED_CONSUMPTION_POLICY))
    assert result.output.actions[0].action_code == "CONTINUE_CONSUMPTION"
    assert result.output.source_diagnosis_ref == diagnosis.output.trace_ref
    assert tools.provenance().decision_ref == result.output.trace_ref


@pytest.mark.parametrize("error,code", [(SystemANotFoundError("private"), "ENTITY_NOT_FOUND"),
    (SystemAUnavailableError("private"), "UPSTREAM_UNAVAILABLE"), (SystemAHTTPError("private"), "UPSTREAM_REJECTED"),
    (SystemAResponseValidationError("private"), "UPSTREAM_INVALID_RESPONSE"), (RuntimeError("private"), "INTERNAL_TOOL_FAILURE")])
def test_upstream_errors_are_typed_and_sanitized(error, code):
    result = load(AgentTools(CanonicalAdapter(error=error)))
    assert result.status == "ERROR" and result.error.code == code and result.output is None
    assert result.error.retryable == (code == "UPSTREAM_UNAVAILABLE")
    assert "private" not in result.model_dump_json()


def test_invalid_request_rejected_before_adapter():
    adapter = CanonicalAdapter()
    result = AgentTools(adapter).get_overdue_po_context(ContextRequest.model_construct(
        request_id="invalid", dataset_version_id=UUID(int=1), snapshot_date=date(2026, 8, 26), po_line_schedule_id=UUID(int=5)))
    assert result.error.code == "INVALID_REQUEST" and not adapter.calls


@pytest.mark.parametrize("tool", ["analytics", "diagnosis", "decision"])
def test_foreign_identity_and_handles_cannot_access_artifacts(tool):
    tools, args, _, diagnosis = prepare()
    args["identity"] = args["identity"].model_copy(update={"material_id": UUID(int=999)})
    if tool == "analytics":
        result = tools.get_overdue_po_analytics(AnalyticsInput(**args))
    elif tool == "diagnosis":
        result = tools.diagnose_overdue_po(DiagnosisInput(**args, policy=policy()))
    else:
        result = tools.get_procurement_decision(DecisionInput(**args, diagnosis_ref=diagnosis.output.trace_ref))
    assert result.error.code == "INVALID_REQUEST" and result.output is None


def test_missing_evidence_stays_unknown_and_unresolved():
    tools, args, analytics, diagnosis = prepare(facts(weekly=None))
    assert analytics.output.metrics.consumption.status == "NOT_COMPUTABLE"
    assert diagnosis.output.status == "UNRESOLVED"
    result = tools.get_procurement_decision(DecisionInput(**args, diagnosis_ref=diagnosis.output.trace_ref))
    assert result.status == "SUCCESS" and result.output.decision_status == "NOT_EVALUABLE"
    assert not result.output.actions


def test_missing_policy_is_not_injected_by_tool():
    tools, args, _, _ = prepare(facts(lifecycle="MASS_PRODUCTION"))
    diagnosis = tools.diagnose_overdue_po(DiagnosisInput(**args))
    assert diagnosis.output.status == "UNRESOLVED" and diagnosis.output.business_policy is None


def test_decision_rejects_stale_diagnosis_ref_after_policy_change():
    tools, args, _, first = prepare()
    second = tools.diagnose_overdue_po(DiagnosisInput(**args, policy=policy(version="fixture-2")))
    assert first.output.trace_ref != second.output.trace_ref
    result = tools.get_procurement_decision(DecisionInput(**args, diagnosis_ref=first.output.trace_ref))
    assert result.error.code == "INVALID_REQUEST"


def test_tool_determinism_and_session_identity_binding():
    adapter = CanonicalAdapter()
    tools = AgentTools(adapter)
    first = load(tools)
    count = len(adapter.calls)
    assert load(tools) == first and len(adapter.calls) == count
    assert load(AgentTools(CanonicalAdapter())) == first
    assert load(tools, request(request_id=UUID(int=801))).error.code == "INVALID_REQUEST"


def test_missing_stable_material_id_blocks_further_retrieval():
    adapter = CanonicalAdapter(facts(po=po(material_id=None)))
    result = load(AgentTools(adapter))
    assert result.error.code == "EVIDENCE_INCOMPLETE" and len(adapter.calls) == 1


def test_out_of_order_tool_call_has_explicit_missing_artifact():
    tools = AgentTools(CanonicalAdapter())
    loaded = load(tools).output
    result = tools.diagnose_overdue_po(DiagnosisInput(identity=loaded.identity, context_ref=loaded.context_ref, policy=policy()))
    assert result.error.code == "EVIDENCE_INCOMPLETE" and result.output is None


def test_tool_schemas_are_explicit_and_versioned():
    assert len(TOOL_CONTRACTS) == 4 and {item.name for item in TOOL_CONTRACTS} == set(ToolName)
    for contract in TOOL_CONTRACTS:
        assert contract.version == "1.0.0"
        assert contract.input_schema.model_json_schema()["additionalProperties"] is False
        assert contract.output_schema.model_json_schema()["additionalProperties"] is False


def test_actual_http_adapter_remains_get_only_and_uses_stable_filters():
    inputs = facts(po=po(inventory_organization_type="TRIAL"))
    req = request(inputs)
    calls = []

    def handler(http_request):
        calls.append(http_request)
        assert http_request.method == "GET"
        name = http_request.url.path.rsplit("/", 1)[1]
        params = http_request.url.params
        assert params["dataset_version_id"] == str(req.dataset_version_id)
        items = []
        if name == "overdue-pos":
            assert params["po_line_schedule_id"] == str(req.po_line_schedule_id)
            items = [source_row(1) | inputs.po.model_dump(mode="json", exclude={"dataset_version_id", "mpm"})]
        else:
            assert params["material_id"] == str(inputs.po.material_id)
        payload = dict(dataset_version_id=str(req.dataset_version_id), snapshot_date=req.snapshot_date.isoformat(),
                       page=int(params["page"]), page_size=int(params["page_size"]), total=len(items), items=items)
        if name == "stockpile":
            assert params["as_of_date"] == inputs.po.order_date.isoformat()
            payload["stockpile_selection"] = dict(as_of_date=params["as_of_date"], stockpile_version_id=None,
                                                  stockpile_version_date=None, sequence_no=None)
        return httpx.Response(200, json=payload)

    with adapter_for(handler) as adapter:
        output = load(AgentTools(adapter), req)
    assert output.status == "SUCCESS" and len(calls) == 6
    assert output.output.missing_sources == ("R2", "R3", "R4", "R5")
