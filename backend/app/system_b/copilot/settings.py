"""Server-process environment only. No credential in the public request."""
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.system_b.diagnosis.parameters import BusinessDiagnosisPolicy
from app.system_b.decision.models import BusinessDecisionPolicy


class CopilotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, env_parse_none_str="null", extra="ignore",
                                     case_sensitive=False, hide_input_in_errors=True)
    openai_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    openai_model: str | None = None
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    openai_max_output_tokens: int = Field(default=4000, ge=256, le=8000)
    openai_temperature: float | None = Field(default=0, ge=0, le=0.3, allow_inf_nan=False)
    copilot_diagnosis_policy: BusinessDiagnosisPolicy | None = None
    copilot_decision_policy: BusinessDecisionPolicy | None = None

    @field_validator("openai_model", mode="before")
    @classmethod
    def blank_model(cls, value):
        return value.strip() or None if isinstance(value, str) else value
