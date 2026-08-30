from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "Overdue PO Copilot - System A"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # Optional for System A startup; required when constructing the System B adapter.
    system_a_base_url: HttpUrl | None = None
    system_a_timeout_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)

    @field_validator("system_a_base_url")
    @classmethod
    def validate_system_a_base_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and (value.username or value.password or value.query or value.fragment):
            raise ValueError("SYSTEM_A_BASE_URL must not include credentials, query or fragment")
        return value

    database_url_owner: SecretStr = SecretStr(
        "postgresql+psycopg://system_a_owner:change_me@localhost:5432/overdue_po_copilot?connect_timeout=3"
    )
    database_url_api: SecretStr = SecretStr(
        "postgresql+psycopg://system_a_api:change_me@localhost:5432/overdue_po_copilot?connect_timeout=3"
    )
    database_url_generator: SecretStr = SecretStr(
        "postgresql+psycopg://system_a_generator:change_me@localhost:5432/overdue_po_copilot?connect_timeout=3"
    )
    database_url_evaluator: SecretStr = SecretStr(
        "postgresql+psycopg://system_a_evaluator:change_me@localhost:5432/overdue_po_copilot?connect_timeout=3"
    )

    @property
    def service_name(self) -> str:
        return "overdue-po-copilot-system-a"

    @property
    def api_database_url(self) -> str:
        return self.database_url_api.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
