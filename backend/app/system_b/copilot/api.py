"""Separate System B application; System A report OpenAPI remains unchanged."""
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.system_b.adapters.system_a import SystemAAdapter
from app.system_b.copilot.models import CopilotRequest, CopilotResponse
from app.system_b.copilot.provider import OpenAILLM
from app.system_b.copilot.service import CopilotService
from app.system_b.copilot.settings import CopilotSettings


def get_copilot_service() -> Iterator[CopilotService]:
    adapter, llm = None, None
    try:
        configured = CopilotSettings()
        adapter = SystemAAdapter()
        llm = OpenAILLM(configured)
        service = CopilotService(adapter, llm, diagnosis_policy=configured.copilot_diagnosis_policy,
                                 decision_policy=configured.copilot_decision_policy)
    except (ValidationError, ValueError):
        if adapter is not None:
            adapter.close()
        raise HTTPException(status_code=503, detail={"code": "COPILOT_CONFIGURATION_UNAVAILABLE"}) from None
    try:
        yield service
    finally:
        llm.close()
        adapter.close()


def create_app() -> FastAPI:
    application = FastAPI(title="Overdue PO Copilot - System B")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic's default error body can echo untrusted query text / secrets.
        return JSONResponse(status_code=422, content={"detail": {"code": "INVALID_REQUEST"}})

    @application.post("/api/v1/copilot/query", response_model=CopilotResponse)
    def query(request: CopilotRequest, service: Annotated[CopilotService, Depends(get_copilot_service)]):
        try:
            return service.query(request)
        except Exception:
            return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_COPILOT_FAILURE"}})

    return application


app = create_app()
