from functools import lru_cache

from pydantic import SecretStr
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
