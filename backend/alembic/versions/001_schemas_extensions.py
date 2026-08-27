"""Create System A schemas and PostgreSQL extensions."""

from alembic import op


revision = "001_schemas_extensions"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")
    op.execute("CREATE SCHEMA IF NOT EXISTS evaluation")
    op.execute("REVOKE ALL ON SCHEMA evaluation FROM PUBLIC")
    op.execute("REVOKE CREATE ON SCHEMA platform FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS evaluation")
    op.execute("DROP SCHEMA IF EXISTS platform")
    # btree_gist is cluster-shared and may be used by other applications; retain it.
