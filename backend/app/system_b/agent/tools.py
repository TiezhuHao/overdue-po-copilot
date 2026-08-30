"""Four typed tools. Artifacts live only in one explicitly scoped tool session."""
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Context, ROUND_HALF_EVEN, localcontext
from hashlib import sha256

from pydantic import ValidationError

from app.system_b.adapters.system_a import SystemAAdapter
from app.system_b.adapters.errors import (
    SystemANotFoundError, SystemAUnavailableError, SystemAHTTPError, SystemAResponseValidationError,
)
from app.system_b.models import CanonicalModel
from app.system_b.diagnosis.models import EvidenceInputs, HistoricalStockpileQuery
from app.system_b.diagnosis.assembler import assemble_evidence, EvidenceAssemblyError
from app.system_b.diagnosis.policy import diagnose_business
from app.system_b.decision.engine import decide, DecisionInputError
from app.system_b.decision.models import DecisionContext
from app.system_b.agent.models import (
    AgentIssue, ErrorCode as E, ToolName as N, ToolResult, ContextRequest, ContextOutput,
    ResolvedIdentity, AnalyticsInput, AnalyticsOutput, DiagnosisInput, DiagnosisOutput,
    DecisionInput, DecisionOutput, Provenance,
)


class ToolFailure(Exception):
    def __init__(self, code: E):
        self.code = code


@dataclass(frozen=True)
class ToolContract:
    name: N
    input_schema: type[CanonicalModel]
    output_schema: type[CanonicalModel]
    version: str = "1.0.0"


TOOL_CONTRACTS = (
    ToolContract(N.CONTEXT, ContextRequest, ToolResult[ContextOutput]),
    ToolContract(N.ANALYTICS, AnalyticsInput, ToolResult[AnalyticsOutput]),
    ToolContract(N.DIAGNOSIS, DiagnosisInput, ToolResult[DiagnosisOutput]),
    ToolContract(N.DECISION, DecisionInput, ToolResult[DecisionOutput]),
)


def _ref(request_id, kind, artifact):
    digest = sha256(artifact.model_dump_json().encode()).hexdigest()
    return f"{request_id}/{kind}/{digest}"


class AgentTools:
    """Create per execution; caller owns adapter lifetime. Never share across runs."""
    def __init__(self, adapter: SystemAAdapter):
        self._adapter = adapter
        self._context = self._inputs = self._bundle = None
        self._diagnosis = self._diagnosis_output = self._decision = None

    def _invoke(self, name, schema, output_schema, request, operation: Callable):
        code = None
        with localcontext(Context(prec=40, rounding=ROUND_HALF_EVEN)):
            try:
                request = schema.model_validate(request.model_dump(warnings=False))
            except (ValidationError, AttributeError, TypeError):
                return ToolResult[output_schema](status="ERROR", error=AgentIssue(code=E.INVALID_REQUEST, tool=name))
            try:
                output = output_schema.model_validate(operation(request).model_dump(warnings=False))
                return ToolResult[output_schema](status="SUCCESS", output=output)
            except ToolFailure as exc:
                code = exc.code
            except SystemANotFoundError:
                code = E.ENTITY_NOT_FOUND
            except SystemAUnavailableError:
                code = E.UPSTREAM_UNAVAILABLE
            except SystemAHTTPError:
                code = E.UPSTREAM_REJECTED
            except SystemAResponseValidationError:
                code = E.UPSTREAM_INVALID_RESPONSE
            except (EvidenceAssemblyError, DecisionInputError):
                code = E.EVIDENCE_INCOMPLETE
            except Exception:
                # Last-resort boundary: no exception text, URLs, bodies or locals.
                code = E.INTERNAL_TOOL_FAILURE
        return ToolResult[output_schema](status="ERROR", error=AgentIssue(
            code=code, tool=name, retryable=code == E.UPSTREAM_UNAVAILABLE))

    def get_overdue_po_context(self, request: ContextRequest) -> ToolResult[ContextOutput]:
        return self._invoke(N.CONTEXT, ContextRequest, ContextOutput, request, self._load)

    def get_overdue_po_analytics(self, request: AnalyticsInput) -> ToolResult[AnalyticsOutput]:
        return self._invoke(N.ANALYTICS, AnalyticsInput, AnalyticsOutput, request, self._analytics)

    def diagnose_overdue_po(self, request: DiagnosisInput) -> ToolResult[DiagnosisOutput]:
        return self._invoke(N.DIAGNOSIS, DiagnosisInput, DiagnosisOutput, request, self._diagnose)

    def get_procurement_decision(self, request: DecisionInput) -> ToolResult[DecisionOutput]:
        return self._invoke(N.DECISION, DecisionInput, DecisionOutput, request, self._decide)

    @staticmethod
    def _page_scope(page, request):
        if page.dataset_version_id != request.dataset_version_id or page.snapshot_date != request.snapshot_date:
            raise ToolFailure(E.UPSTREAM_INVALID_RESPONSE)

    def _load(self, request):
        if self._context is not None:
            known = ContextRequest(**self._context.identity.model_dump(include=set(ContextRequest.model_fields)))
            if known != request:
                raise ToolFailure(E.INVALID_REQUEST)
            return self._context
        adapter, did = self._adapter, request.dataset_version_id
        po_page = adapter.purchase_orders(did, po_line_schedule_id=request.po_line_schedule_id)
        self._page_scope(po_page, request)
        if po_page.total == 0:
            raise ToolFailure(E.ENTITY_NOT_FOUND)
        if po_page.total != 1 or len(po_page.items) != 1:
            raise ToolFailure(E.UPSTREAM_INVALID_RESPONSE)
        po = po_page.items[0]
        if (po.po_line_schedule_id != request.po_line_schedule_id
                or po.dataset_version_id != request.dataset_version_id or po.snapshot_date != request.snapshot_date):
            raise ToolFailure(E.UPSTREAM_INVALID_RESPONSE)
        fields = ("po_header_id", "po_line_id", "material_id", "organization_id", "supplier_id")
        if any(getattr(po, field) is None for field in fields):
            raise ToolFailure(E.EVIDENCE_INCOMPLETE)
        identity = ResolvedIdentity(**request.model_dump(), **{field: getattr(po, field) for field in fields})

        def collect(method, **filters):
            rows = []
            for page in adapter.iter_pages(method, did, material_id=po.material_id, **filters):
                self._page_scope(page, request)
                rows.extend(page.items)
            return tuple(rows)

        supply = collect(adapter.material_supply_demand)
        weekly = collect(adapter.latest_13w_forecast)
        if len(supply) > 1 or len(weekly) > 1:
            raise ToolFailure(E.UPSTREAM_INVALID_RESPONSE)
        history = collect(adapter.forecast_history, po_line_schedule_id=po.po_line_schedule_id)
        products = collect(adapter.product_configurations)
        stockpile = adapter.stockpile(did, material_id=po.material_id, as_of_date=po.order_date)
        self._page_scope(stockpile, request)
        if stockpile.total != len(stockpile.items) or stockpile.total > 1:
            raise ToolFailure(E.UPSTREAM_INVALID_RESPONSE)
        inputs = EvidenceInputs(po=po, supply=supply[0] if supply else None, weekly=weekly[0] if weekly else None,
            forecast_history=history, products=products, stockpile=HistoricalStockpileQuery(
                material_id=po.material_id, as_of_date=po.order_date, page=stockpile))
        # Input is canonical; Analytics tool performs the existing assembly/derivation.
        output = ContextOutput(identity=identity, context_ref=_ref(request.request_id, "context", inputs),
            missing_sources=tuple(label for label, rows in (("R2", supply), ("R3", history), ("R4", weekly), ("R5", products)) if not rows))
        self._inputs, self._context = inputs, output
        return output

    def _check_context(self, request):
        if self._context is None:
            raise ToolFailure(E.EVIDENCE_INCOMPLETE)
        if request.identity != self._context.identity or request.context_ref != self._context.context_ref:
            raise ToolFailure(E.INVALID_REQUEST)

    def _analytics(self, request):
        self._check_context(request)
        bundle = assemble_evidence(self._inputs)
        self._bundle = bundle
        return AnalyticsOutput(**request.model_dump(), metrics=bundle.analytics, missing_evidence=bundle.missing_evidence)

    def _diagnose(self, request):
        self._check_context(request)
        if self._bundle is None:
            raise ToolFailure(E.EVIDENCE_INCOMPLETE)
        result = diagnose_business(self._bundle, request.policy)
        values = result.model_dump(include=set(DiagnosisOutput.model_fields))
        output = DiagnosisOutput(**values, identity=request.identity, context_ref=request.context_ref,
            trace_ref=_ref(request.identity.request_id, "diagnosis", result))
        self._diagnosis, self._diagnosis_output, self._decision = result, output, None
        return output

    def _decide(self, request):
        self._check_context(request)
        if self._diagnosis is None:
            raise ToolFailure(E.EVIDENCE_INCOMPLETE)
        if request.diagnosis_ref != self._diagnosis_output.trace_ref:
            raise ToolFailure(E.INVALID_REQUEST)
        result = decide(DecisionContext(diagnosis=self._diagnosis, evidence=self._bundle, policy=request.policy))
        output = DecisionOutput(**result.model_dump(include=set(DecisionOutput.model_fields)),
            identity=request.identity, context_ref=request.context_ref,
            source_diagnosis_ref=request.diagnosis_ref, trace_ref=_ref(request.identity.request_id, "decision", result))
        self._decision = result
        return output

    def provenance(self) -> Provenance:
        """Export each fact once before discarding the execution session."""
        return Provenance(context_ref=self._context.context_ref if self._context else None,
            diagnosis_ref=self._diagnosis_output.trace_ref if self._diagnosis_output else None,
            decision_ref=_ref(self._context.identity.request_id, "decision", self._decision) if self._decision else None,
            facts=self._decision.evidence_trace if self._decision else self._diagnosis.evidence_trace if self._diagnosis else ())
