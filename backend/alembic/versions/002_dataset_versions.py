"""Create dataset version metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "002_dataset_versions"
down_revision = "001_schemas_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_name", sa.String(length=200), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("generation_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generation_signature", sa.String(length=128), nullable=False),
        sa.Column("business_content_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('GENERATING', 'READY', 'FAILED', 'RETIRED')",
            name="ck_dataset_versions_dataset_status",
        ),
        sa.PrimaryKeyConstraint("dataset_version_id", name="pk_dataset_versions"),
        sa.UniqueConstraint("generation_signature", name="uq_dataset_versions_generation_signature"),
        sa.UniqueConstraint("version_name", name="uq_dataset_versions_version_name"),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("dataset_versions", schema="platform")
