import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--run-llm-integration", action="store_true", default=False,
                     help="Explicitly opt in to paid provider smoke tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-llm-integration"):
        return
    excluded = [item for item in items if item.get_closest_marker("llm_integration")]
    if excluded:
        config.hook.pytest_deselected(items=excluded)
        items[:] = [item for item in items if not item.get_closest_marker("llm_integration")]


class _RedactedDatabaseURL(str):
    """Keep pytest argument rendering from revealing local connection passwords."""

    def __repr__(self) -> str:
        return make_url(self).render_as_string(hide_password=True)


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _disposable_database_url(env_name: str) -> str:
    database_url = os.getenv(env_name)
    if not database_url:
        pytest.skip(f"{env_name} is not configured")
    database_name = make_url(database_url).database or ""
    if "test" not in database_name.lower():
        pytest.fail(f"{env_name} must target a database whose name contains 'test'")
    return _RedactedDatabaseURL(database_url)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _disposable_database_url("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> Iterator[Engine]:
    engine = create_engine(test_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc.__class__.__name__}")

    previous_owner_url = os.environ.get("DATABASE_URL_OWNER")
    os.environ["DATABASE_URL_OWNER"] = test_database_url
    config = alembic_config(test_database_url)
    try:
        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT count(*) FROM information_schema.schemata "
                     "WHERE schema_name IN ('platform', 'evaluation')")
            ) == 0
            assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
        command.upgrade(config, "head")
        # Dropping a schema removes its default ACLs too. Reapply the established
        # owner bootstrap after rebuilding so isolated test modules see real grants.
        with engine.begin() as connection:
            connection.exec_driver_sql(
                (BACKEND_ROOT / "db/bootstrap/002_grants.sql").read_text(encoding="utf-8")
            )
        yield engine
    finally:
        engine.dispose()
        if previous_owner_url is None:
            os.environ.pop("DATABASE_URL_OWNER", None)
        else:
            os.environ["DATABASE_URL_OWNER"] = previous_owner_url


@pytest.fixture()
def database_connection(migrated_database: Engine):
    with migrated_database.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()
