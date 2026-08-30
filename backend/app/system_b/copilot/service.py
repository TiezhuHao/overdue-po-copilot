"""Bounded intent routing, exact resolver, existing graph and checked answers."""
from decimal import Context, ROUND_HALF_EVEN, localcontext

from pydantic import ValidationError

from app.system_b.adapters.errors import (
    SystemANotFoundError, SystemAUnavailableError, SystemAHTTPError, SystemAResponseValidationError,
)
from app.system_b.agent.graph import ProcurementAgent
from app.system_b.agent.models import AgentRequest
from app.system_b.copilot.models import (
    CopilotRequest, CopilotResponse, IntentDraft, Intent, EvaluationHook, PublicDiagnosis, PublicDecision, PublicAction,
)
from app.system_b.copilot.provider import LLMClient, LLMFailure
from app.system_b.copilot.resolver import resolve, SelectorError
from app.system_b.copilot.grounding import project_execution, validate_draft, fallback_draft, render, GroundingError


QUESTIONS = {
    "MISSING_DATASET": "请先指定要查询的数据集；不会自动选择最新数据集。",
    "MISSING_PO_OR_MATERIAL": "请提供 PO 号、物料编码或明确的发运行 ID。",
    "AMBIGUOUS_PO": "查询匹配到多个发运行，请补充组织、PO 行号、发运号或明确的发运行 ID。",
    "SNAPSHOT_MISMATCH": "给定 snapshot 与数据集不一致，请确认数据集和日期。",
    "DATASET_NOT_READY": "该数据集尚未处于 READY 状态，请选择已就绪的数据集。",
    "MISSING_STABLE_ID": "匹配记录缺少稳定身份，当前不能继续分析。",
    "PO_NOT_IN_REPORT": "在指定数据集的超期 PO 报表中未找到精确匹配；这不证明其他报表中不存在该订单。",
    "UNSUPPORTED_REQUEST": "当前只支持只读的 PO 分析、指标、原因解释和处置建议，不执行采购操作。",
    "LLM_PARSE_FAILED": "当前无法可靠解析文本，请补充明确的 PO 号、物料编码或发运行 ID。",
    "CONFLICTING_SELECTOR": "提供的查询条件有冲突或无法从原文核验，请确认 PO、物料和已知身份。",
}


class CopilotService:
    def __init__(self, adapter, llm: LLMClient, *, diagnosis_policy=None, decision_policy=None):
        self.adapter, self.llm = adapter, llm
        # Trusted server configuration only; never supplied by the model or public query.
        self.diagnosis_policy, self.decision_policy = diagnosis_policy, decision_policy

    def query(self, request: CopilotRequest) -> CopilotResponse:
        with localcontext(Context(prec=40, rounding=ROUND_HALF_EVEN)):
            return self._query(CopilotRequest.model_validate(request.model_dump(warnings=False)))

    def _query(self, request):
        intent, parsing_issue = None, None

        def clarification(code, status="NEEDS_CLARIFICATION", candidates=()):
            return CopilotResponse(request_id=request.request_id, status=status, answer=QUESTIONS[code],
                answer_source="CLARIFICATION", intent=intent, limitations=(code,), candidate_schedule_ids=candidates,
                evaluation=EvaluationHook(resolved_intent=intent))

        if request.dataset_version_id is None:
            return clarification("MISSING_DATASET")
        try:
            parsed = self.llm.parse_intent(request.user_query)
            parsed = IntentDraft.model_validate(parsed.model_dump(warnings=False))
        except LLMFailure as exc:
            parsed, parsing_issue = None, exc.code
        except Exception:
            parsed, parsing_issue = None, "LLM_INVALID_RESPONSE"
        if parsed is None:
            if not (request.po_line_schedule_id or request.po_number or request.material_code):
                return clarification("LLM_PARSE_FAILED")
            # Known structured selectors permit a read-only full analysis without guessing text entities.
            parsed = IntentDraft(intent=Intent.ANALYZE_OVERDUE_PO, po_number=None, material_code=None)
        intent = parsed.intent
        if intent == Intent.UNSUPPORTED:
            return clarification("UNSUPPORTED_REQUEST")
        try:
            resolution = resolve(self.adapter, request, parsed)
        except SelectorError:
            return clarification("CONFLICTING_SELECTOR")
        except SystemANotFoundError:
            return clarification("PO_NOT_IN_REPORT", "NOT_FOUND")
        except (SystemAUnavailableError, SystemAHTTPError, SystemAResponseValidationError) as exc:
            code = ("UPSTREAM_UNAVAILABLE" if isinstance(exc, SystemAUnavailableError) else
                    "UPSTREAM_REJECTED" if isinstance(exc, SystemAHTTPError) else "UPSTREAM_INVALID_RESPONSE")
            return CopilotResponse(request_id=request.request_id, status="FAILED", answer="上游查询未能完成，当前不生成业务判断。",
                answer_source="FALLBACK", intent=intent, limitations=(code,), evaluation=EvaluationHook(resolved_intent=intent))
        if resolution.status != "RESOLVED":
            return clarification(resolution.clarification_code, resolution.status, resolution.candidate_schedule_ids)
        # All supported intents use the same dependency-safe four-tool graph. Intent controls presentation only.
        execution = ProcurementAgent(self.adapter).execute(AgentRequest(request_id=request.request_id,
            dataset_version_id=request.dataset_version_id, snapshot_date=resolution.snapshot_date,
            po_line_schedule_id=resolution.po_line_schedule_id, diagnosis_policy=self.diagnosis_policy,
            decision_policy=self.decision_policy))
        packet = project_execution(execution)
        source, failure = "FALLBACK", parsing_issue
        draft = fallback_draft(packet)
        if failure is None:
            try:
                draft = validate_draft(packet, self.llm.compose(packet, intent))
                source = "MODEL"
            except LLMFailure as exc:
                failure = exc.code
            except (GroundingError, ValidationError, AttributeError):
                failure = "GROUNDING_REJECTED"
            except Exception:
                failure = "LLM_INVALID_RESPONSE"
        # Never retain rejected text. The fallback is independently constructed from the same packet.
        if source == "FALLBACK":
            draft = fallback_draft(packet)
        diagnosis = execution.diagnosis
        decision = execution.decision
        limitations = tuple(fact.allowed_sentences[0] for fact in packet.facts if fact.section == "数据 / 规则限制")
        if failure:
            limitations += (failure,)
        return CopilotResponse(request_id=request.request_id, status=execution.status, answer=render(draft), answer_source=source,
            resolved_identity=execution.resolved_identity, intent=intent, key_metrics=packet.metrics,
            diagnosis=PublicDiagnosis(status=diagnosis.status, primary_reason=diagnosis.primary_reason,
                primary_rule_id=diagnosis.primary_rule_id, primary_rule_version=diagnosis.primary_rule_version,
                supporting_signals=diagnosis.signals) if diagnosis else None,
            decision=PublicDecision(status=decision.decision_status, rule_id=decision.decision_rule_id,
                rule_version=decision.decision_rule_version, owner_role=decision.owner_role,
                actions=tuple(PublicAction(action_code=action.action_code, owner_role=action.owner_role,
                                          required=action.required) for action in decision.actions)) if decision else None,
            evidence_references=packet.evidence_references, limitations=limitations, execution_reference=request.request_id,
            evaluation=EvaluationHook(resolved_intent=intent,
                tool_path=tuple(entry.tool.value for entry in execution.execution_trace if entry.tool),
                business_status=execution.status, grounding_status="VALIDATED" if source == "MODEL" else "FALLBACK"))
