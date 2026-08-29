"""Create six canonical report semantics and normalized helpers."""
from alembic import op

from app.reporting.view_definitions import create_statements, drop_statements


revision = '011_report_semantic_views'
down_revision = '010_operational_evidence'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE SCHEMA reporting')
    for statement in create_statements():
        op.execute(statement)
    op.execute('GRANT USAGE ON SCHEMA reporting TO system_a_api, system_a_evaluator')
    op.execute('GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO system_a_api, system_a_evaluator')
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE system_a_owner IN SCHEMA reporting GRANT SELECT ON TABLES TO system_a_api, system_a_evaluator")


def downgrade():
    for statement in drop_statements():
        op.execute(statement)
    op.execute('DROP SCHEMA reporting')
