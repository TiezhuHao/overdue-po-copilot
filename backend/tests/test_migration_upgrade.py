from io import StringIO

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.conftest import alembic_config


def test_migrations_render_for_postgresql() -> None:
    output = StringIO()
    config = alembic_config(
        "postgresql+psycopg://system_a_owner:unused@localhost/system_a_offline"
    )
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    ddl = output.getvalue()
    assert "CREATE SCHEMA IF NOT EXISTS platform" in ddl
    assert "CREATE SCHEMA IF NOT EXISTS evaluation" in ddl
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in ddl
    assert "CREATE TABLE platform.dataset_versions" in ddl
    assert "CREATE TABLE platform.employee_role_assignments" in ddl
    assert "CREATE TABLE platform.material_supplier_assignments" in ddl
    assert "CREATE TABLE platform.project_customers" in ddl
    assert "CREATE TABLE platform.material_responsibility_assignments" in ddl
    assert "CREATE TABLE platform.po_headers" in ddl
    assert "CREATE TABLE platform.po_lines" in ddl
    assert "CREATE TABLE platform.po_line_schedules" in ddl
    assert "CREATE TABLE evaluation.scenario_truth" in ddl
    assert "CREATE TABLE platform.project_lifecycle_history" in ddl
    assert "CREATE TABLE platform.demand_signal_revisions" in ddl
    assert "EXCLUDE USING gist" in ddl


@pytest.mark.integration
def test_migration_upgrade_reaches_head(migrated_database: Engine) -> None:
    with migrated_database.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        schemas = set(
            connection.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name IN ('platform', 'evaluation')"
                )
            ).scalars()
        )
    assert revision == "008_evidence_foundation"
    assert schemas == {"platform", "evaluation"}
