from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class ReadinessError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        database: str = "unknown",
        migration: str = "unknown",
    ) -> None:
        super().__init__(message)
        self.database = database
        self.migration = migration


@dataclass(frozen=True)
class ReadinessResult:
    database: str
    migration: str


class ReadinessChecker:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> ReadinessResult:
        expected_head = self._expected_alembic_head()
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise ReadinessError(
                "database connectivity check failed",
                database="unavailable",
            ) from exc

        try:
            with self._engine.connect() as connection:
                current_revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
        except Exception as exc:
            raise ReadinessError(
                "Alembic revision check failed",
                database="ok",
                migration="unavailable",
            ) from exc

        if current_revision != expected_head:
            raise ReadinessError(
                "database migration is not at Alembic head",
                database="ok",
                migration="out_of_date",
            )
        return ReadinessResult(database="ok", migration="ok")

    @staticmethod
    def _expected_alembic_head() -> str:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        if head is None:
            raise ReadinessError("Alembic head is not defined")
        return head
