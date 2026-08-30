"""Official Responses API isolated from all procurement tools and engines."""
import json
from typing import Protocol

import httpx2
from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError
from pydantic import ValidationError

from app.system_b.copilot.models import Intent, IntentDraft, GroundingPacket, CopilotAnswerDraft
from app.system_b.copilot.prompts import INTENT_PROMPT, COMPOSITION_PROMPT
from app.system_b.copilot.settings import CopilotSettings


class LLMFailure(RuntimeError):
    """Stable code only; never retain the provider body or exception text."""
    def __init__(self, code: str):
        if code not in {"LLM_NOT_CONFIGURED", "LLM_TIMEOUT", "LLM_UNAVAILABLE",
                        "LLM_REJECTED_REQUEST", "LLM_INVALID_RESPONSE"}:
            code = "LLM_INVALID_RESPONSE"
        super().__init__(code)
        self.code = code


class LLMClient(Protocol):
    def parse_intent(self, user_query: str) -> IntentDraft: ...
    def compose(self, packet: GroundingPacket, intent: Intent) -> CopilotAnswerDraft: ...


class OpenAILLM:
    def __init__(self, settings: CopilotSettings, *, transport: httpx2.BaseTransport | None = None):
        self._settings = settings
        self._client = None
        if settings.openai_api_key and settings.openai_api_key.get_secret_value() and settings.openai_model:
            self._client = OpenAI(api_key=settings.openai_api_key.get_secret_value(),
                base_url="https://api.openai.com/v1", max_retries=0,
                timeout=settings.openai_timeout_seconds,
                http_client=httpx2.Client(transport=transport, follow_redirects=False, trust_env=False,
                                         timeout=settings.openai_timeout_seconds))

    def close(self):
        if self._client is not None:
            self._client.close()

    def _parse(self, prompt, content, schema):
        if self._client is None:
            raise LLMFailure("LLM_NOT_CONFIGURED")
        options = {}
        if self._settings.openai_temperature is not None:
            options["temperature"] = self._settings.openai_temperature
        try:
            response = self._client.responses.parse(
                model=self._settings.openai_model, store=False,
                input=[{"role": "system", "content": prompt}, {"role": "user", "content": content}],
                text_format=schema, max_output_tokens=self._settings.openai_max_output_tokens, **options)
            if response.status != "completed" or response.output_parsed is None:
                raise LLMFailure("LLM_INVALID_RESPONSE")
            return schema.model_validate(response.output_parsed.model_dump(warnings=False))
        except APITimeoutError:
            raise LLMFailure("LLM_TIMEOUT") from None
        except APIConnectionError:
            raise LLMFailure("LLM_UNAVAILABLE") from None
        except APIStatusError:
            raise LLMFailure("LLM_REJECTED_REQUEST") from None
        except (ValidationError, ValueError):
            raise LLMFailure("LLM_INVALID_RESPONSE") from None

    def parse_intent(self, user_query: str) -> IntentDraft:
        return self._parse(INTENT_PROMPT, user_query, IntentDraft)

    def compose(self, packet: GroundingPacket, intent: Intent) -> CopilotAnswerDraft:
        content = json.dumps({"intent": intent.value, "grounding": packet.model_dump(mode="json")}, ensure_ascii=False)
        return self._parse(COMPOSITION_PROMPT, content, CopilotAnswerDraft)
