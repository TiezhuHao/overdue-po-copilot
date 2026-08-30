"""Deterministic LangGraph execution. No model, persistence, retries or writes."""
from decimal import Context, ROUND_HALF_EVEN, localcontext

from langgraph.graph import StateGraph, START, END
from langsmith import tracing_context
from pydantic import ValidationError

from app.system_b.adapters.system_a import SystemAAdapter
from app.system_b.agent.models import (
    AgentRequest, AgentExecutionResult, AgentIssue, ErrorCode as E, ExecutionTrace,
    ContextRequest, AnalyticsInput, DiagnosisInput, DecisionInput, ToolName as N,
)
from app.system_b.agent.state import AgentState
from app.system_b.agent.tools import AgentTools


def _build_graph(tools: AgentTools):
    """Internal graph factory; each invocation must have its own tool session."""
    def trace(state, node, status, path, tool=None, ref=None):
        request = state["request"]
        return (*state.get("execution_trace", ()), ExecutionTrace(
            sequence=len(state.get("execution_trace", ())) + 1, node=node, tool=tool,
            input_identity=state["context"].identity if state.get("context") else ContextRequest(
                **request.model_dump(include=set(ContextRequest.model_fields))),
            result_status=status, selected_path=path, downstream_trace_ref=ref))

    def record(state, node, tool, result, output_key, next_node):
        failed = result.status == "ERROR"
        updates = {"selected_tool": tool}
        ref = None
        status = result.status
        if failed:
            updates["errors"] = (*state.get("errors", ()), result.error)
        else:
            updates[output_key] = result.output
            ref = getattr(result.output, "trace_ref", getattr(result.output, "context_ref", None))
            status = getattr(result.output, "status", getattr(result.output, "decision_status", status))
        updates["execution_trace"] = trace(state, node, status, "structured_result" if failed else next_node, tool, ref)
        return updates

    def validate_request(state: AgentState):
        return {"execution_trace": trace(state, "validate_request", "VALID", "load_context")}

    def load_context(state: AgentState):
        request = ContextRequest(**state["request"].model_dump(include=set(ContextRequest.model_fields)))
        return record(state, "load_context", N.CONTEXT, tools.get_overdue_po_context(request), "context", "analytics")

    def analytics(state: AgentState):
        context = state["context"]
        return record(state, "analytics", N.ANALYTICS, tools.get_overdue_po_analytics(
            AnalyticsInput(identity=context.identity, context_ref=context.context_ref)), "analytics", "diagnosis")

    def diagnosis(state: AgentState):
        context = state["context"]
        return record(state, "diagnosis", N.DIAGNOSIS, tools.diagnose_overdue_po(DiagnosisInput(
            identity=context.identity, context_ref=context.context_ref, policy=state["request"].diagnosis_policy)),
            "diagnosis", "decision")

    def decision(state: AgentState):
        context = state["context"]
        return record(state, "decision", N.DECISION, tools.get_procurement_decision(DecisionInput(
            identity=context.identity, context_ref=context.context_ref, diagnosis_ref=state["diagnosis"].trace_ref,
            policy=state["request"].decision_policy)), "decision", "structured_result")

    def structured_result(state: AgentState):
        errors = state.get("errors", ())
        context, decision_result = state.get("context"), state.get("decision")
        status = "FAILED"
        if not errors and decision_result is not None:
            status = {"DECIDED": "COMPLETED", "NOT_APPLICABLE": "NOT_APPLICABLE",
                      "NOT_EVALUABLE": "UNRESOLVED"}[decision_result.decision_status]
            if status == "UNRESOLVED":
                errors += (AgentIssue(code=E.BUSINESS_UNRESOLVED, tool=N.DECISION),)
        if context and context.missing_sources:
            errors += (AgentIssue(code=E.EVIDENCE_INCOMPLETE, tool=N.CONTEXT, blocking=False),)
        final_trace = trace(state, "structured_result", status, "END")
        result = AgentExecutionResult(status=status, request=state["request"],
            resolved_identity=context.identity if context else None, analytics=state.get("analytics"),
            diagnosis=state.get("diagnosis"), decision=decision_result, execution_trace=final_trace, issues=errors,
            unresolved_requirements=decision_result.unresolved_requirements if decision_result else (),
            provenance=tools.provenance())
        return {"result": result, "execution_trace": final_trace, "selected_tool": None}

    builder = StateGraph(AgentState)
    nodes = {"validate_request": validate_request, "load_context": load_context, "analytics": analytics,
             "diagnosis": diagnosis, "decision": decision, "structured_result": structured_result}
    for name, node in nodes.items():
        builder.add_node(name, node)
    builder.add_edge(START, "validate_request")
    builder.add_edge("validate_request", "load_context")
    for current, following in (("load_context", "analytics"), ("analytics", "diagnosis"), ("diagnosis", "decision")):
        builder.add_conditional_edges(current, lambda state: "failed" if state.get("errors") else "continue",
                                      {"failed": "structured_result", "continue": following})
    builder.add_edge("decision", "structured_result")
    builder.add_edge("structured_result", END)
    return builder.compile()  # No checkpointer or external store.


class ProcurementAgent:
    """Public entry point; fresh state/artifacts per call, no caller callbacks."""
    def __init__(self, adapter: SystemAAdapter):
        self._adapter = adapter

    def execute(self, request: AgentRequest) -> AgentExecutionResult:
        with localcontext(Context(prec=40, rounding=ROUND_HALF_EVEN)), tracing_context(enabled=False, parent=False):
            try:
                request = AgentRequest.model_validate(request.model_dump(warnings=False))
            except (ValidationError, AttributeError, TypeError):
                return AgentExecutionResult(status="FAILED", request=None,
                    issues=(AgentIssue(code=E.INVALID_REQUEST),), execution_trace=(ExecutionTrace(
                        sequence=1, node="validate_request", result_status="INVALID_REQUEST", selected_path="END"),))
            tools = AgentTools(self._adapter)
            try:
                return _build_graph(tools).invoke({"request": request, "errors": (), "execution_trace": ()},
                                                config={"recursion_limit": 10, "callbacks": []})["result"]
            except Exception:
                # Framework failures are sanitized too; no exception body escapes.
                return AgentExecutionResult(status="FAILED", request=request,
                    issues=(AgentIssue(code=E.INTERNAL_TOOL_FAILURE),), execution_trace=(ExecutionTrace(
                        sequence=1, node="graph", result_status="INTERNAL_TOOL_FAILURE", selected_path="END"),))
