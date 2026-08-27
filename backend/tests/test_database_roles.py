import os
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url

from app.core.config import settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _execute_sql_script(connection: Connection, script: str) -> None:
    """Execute a trusted bootstrap script without DBAPI parameter parsing."""
    driver_connection = connection.connection.driver_connection
    with driver_connection.cursor() as cursor:
        cursor.execute(script)


def test_role_sql_encodes_evaluation_isolation() -> None:
    roles_sql = (BACKEND_ROOT / "db" / "bootstrap" / "001_roles.sql").read_text(
        encoding="utf-8"
    )
    grants_sql = (BACKEND_ROOT / "db" / "bootstrap" / "002_grants.sql").read_text(
        encoding="utf-8"
    )
    for role in (
        "system_a_owner",
        "system_a_generator",
        "system_a_api",
        "system_a_evaluator",
    ):
        assert role in roles_sql
    assert "REVOKE ALL ON SCHEMA evaluation FROM system_a_api" in grants_sql
    assert "GRANT SELECT ON TABLE platform.dataset_versions TO system_a_api" in grants_sql
    assert "GRANT SELECT ON TABLE public.alembic_version TO system_a_api" in grants_sql


@pytest.mark.integration
def test_api_role_has_no_evaluation_privileges(migrated_database: Engine) -> None:
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL is not configured")

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            _execute_sql_script(
                connection,
                (BACKEND_ROOT / "db" / "bootstrap" / "001_roles.sql").read_text(
                    encoding="utf-8"
                ),
            )
            _execute_sql_script(
                connection,
                (BACKEND_ROOT / "db" / "bootstrap" / "002_grants.sql").read_text(
                    encoding="utf-8"
                ),
            )
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS evaluation.phase1_permission_probe "
                    "(probe_id integer)"
                )
            )
            can_use = connection.execute(
                text("SELECT has_schema_privilege('system_a_api', 'evaluation', 'USAGE')")
            ).scalar_one()
            can_create = connection.execute(
                text("SELECT has_schema_privilege('system_a_api', 'evaluation', 'CREATE')")
            ).scalar_one()
            can_select = connection.execute(
                text(
                    "SELECT has_table_privilege(" 
                    "'system_a_api', 'evaluation.phase1_permission_probe', 'SELECT')"
                )
            ).scalar_one()
            can_read_dataset = connection.execute(
                text(
                    "SELECT has_table_privilege(" 
                    "'system_a_api', 'platform.dataset_versions', 'SELECT')"
                )
            ).scalar_one()
            can_read_alembic_version = connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'system_a_api', 'public.alembic_version', 'SELECT')"
                )
            ).scalar_one()
            api_can_read_po_raw = connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'system_a_api', 'platform.po_headers', 'SELECT')"
                )
            ).scalar_one()
            generator_can_write_po = connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'system_a_generator', 'platform.po_headers', 'INSERT')"
                )
            ).scalar_one()
            api_can_read_truth = connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'system_a_api', 'evaluation.scenario_truth', 'SELECT')"
                )
            ).scalar_one()
            evaluator_can_read_truth = connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'system_a_evaluator', 'evaluation.scenario_truth', 'SELECT')"
                )
            ).scalar_one()
            generator_can_write_truth = connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'system_a_generator', 'evaluation.scenario_truth', 'INSERT')"
                )
            ).scalar_one()
            connection.execute(text("SET ROLE system_a_api"))
            with pytest.raises(DBAPIError) as denied:
                connection.execute(text("SELECT * FROM evaluation.scenario_truth LIMIT 1"))
            assert denied.value.orig.sqlstate == "42501"
            connection.execute(text("RESET ROLE"))
            connection.execute(text("DROP TABLE evaluation.phase1_permission_probe"))
    finally:
        admin_engine.dispose()

    assert can_use is False
    assert can_create is False
    assert can_select is False
    assert can_read_dataset is True
    assert can_read_alembic_version is True
    assert api_can_read_po_raw is False
    assert generator_can_write_po is True
    assert api_can_read_truth is False
    assert evaluator_can_read_truth is True
    assert generator_can_write_truth is True


@pytest.mark.integration
@pytest.mark.parametrize("role", ["api", "generator", "evaluator"])
def test_real_role_login_enforces_truth_access(
    migrated_database: Engine, test_database_url: str, role: str,
) -> None:
    credentials = make_url(getattr(settings, f"database_url_{role}").get_secret_value())
    # Reuse the disposable database endpoint, never write to the configured dev DB.
    url = make_url(test_database_url).set(
        username=credentials.username, password=credentials.password
    )
    role_engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with role_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == f"system_a_{role}"
            if role == "api":
                with pytest.raises(DBAPIError) as denied:
                    connection.execute(text("SELECT * FROM evaluation.scenario_truth LIMIT 1"))
                assert denied.value.orig.sqlstate == "42501"
            else:
                connection.execute(text("SELECT * FROM evaluation.scenario_truth LIMIT 1"))
                statements = (
                    "INSERT INTO evaluation.scenario_truth SELECT * FROM evaluation.scenario_truth WHERE false",
                    "UPDATE evaluation.scenario_truth SET expected_action = NULL WHERE false",
                    "DELETE FROM evaluation.scenario_truth WHERE false",
                )
                for statement in statements:
                    if role == "generator":
                        # PostgreSQL checks privileges even when no rows are changed.
                        assert connection.execute(text(statement)).rowcount == 0
                    else:
                        with pytest.raises(DBAPIError) as denied:
                            connection.execute(text(statement))
                        assert denied.value.orig.sqlstate == "42501"
    finally:
        role_engine.dispose()
