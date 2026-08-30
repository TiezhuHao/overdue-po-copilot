"""Add narrowly projected evidence views; preserve existing report/Excel views."""
from alembic import op

from app.reporting.evidence_views import create_statements, drop_statements

revision = "012_evidence_contract"
down_revision = "011_report_semantic_views"
branch_labels = None
depends_on = None


def upgrade():
    for statement in create_statements():
        op.execute(statement)
    from app.reporting.evidence_views import VIEWS
    for name in VIEWS:
        op.execute(f"GRANT SELECT ON reporting.{name} TO system_a_api, system_a_evaluator")


def downgrade():
    for statement in drop_statements():
        op.execute(statement)
