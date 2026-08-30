"""Only projections and artifact references enter LangGraph channels."""
from typing import TypedDict

from app.system_b.agent.models import (
    AgentRequest, AgentExecutionResult, AgentIssue, ToolName, ContextOutput,
    AnalyticsOutput, DiagnosisOutput, DecisionOutput, ExecutionTrace,
)


class AgentState(TypedDict, total=False):
    request: AgentRequest
    selected_tool: ToolName | None
    context: ContextOutput
    analytics: AnalyticsOutput
    diagnosis: DiagnosisOutput
    decision: DecisionOutput
    errors: tuple[AgentIssue, ...]
    execution_trace: tuple[ExecutionTrace, ...]
    result: AgentExecutionResult
