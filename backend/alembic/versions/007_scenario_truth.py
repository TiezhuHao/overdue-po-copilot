"""Create isolated Phase 4 scenario evaluation truth."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "007_scenario_truth"
down_revision = "006_procurement_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_truth",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_truth_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_line_schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_pattern", sa.String(80), nullable=False),
        sa.Column("true_cause", sa.String(64), nullable=False),
        sa.Column("true_cause_subtype", sa.String(32), nullable=False),
        sa.Column("causal_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("demand_change_type", sa.String(32), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("stockpile_flag", sa.Boolean(), nullable=False),
        sa.Column("responsibility_type", sa.String(32), nullable=True),
        sa.Column("expected_action", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "po_line_schedule_id"],
            ["platform.po_line_schedules.dataset_version_id", "platform.po_line_schedules.po_line_schedule_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "po_line_id"],
            ["platform.po_lines.dataset_version_id", "platform.po_lines.po_line_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "causal_project_id"],
            ["platform.projects.dataset_version_id", "platform.projects.project_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "scenario_pattern IN ('TRIAL', 'DEMAND_REDUCTION', 'DEMAND_DELAY', "
            "'DEMAND_MIXED', 'CUSTOMER_SIDE_PROJECT_OBSOLESCENCE', 'AFTER_SALES', "
            "'STOCKPILE', 'INTERNAL_SIDE_PROJECT_OBSOLESCENCE')",
            name="ck_scenario_truth_pattern",
        ),
        sa.CheckConstraint(
            "true_cause IN ('TRIAL', 'STOCKPILE', 'DEMAND_ADJUSTMENT', "
            "'AFTER_SALES', 'PROJECT_OBSOLESCENCE')",
            name="ck_scenario_truth_cause",
        ),
        sa.CheckConstraint(
            "true_cause_subtype IN ('REDUCTION', 'DELAY', 'MIXED', 'NONE')",
            name="ck_scenario_truth_subtype",
        ),
        sa.CheckConstraint(
            "demand_change_type IN ('REDUCTION', 'DELAY', 'MIXED', 'NONE')",
            name="ck_scenario_truth_demand_change",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('NPI', 'MASS_PRODUCTION', 'EOL')",
            name="ck_scenario_truth_lifecycle",
        ),
        sa.CheckConstraint(
            "responsibility_type IS NULL OR responsibility_type IN "
            "('CUSTOMER_SIDE', 'INTERNAL_SIDE', 'MPM')",
            name="ck_scenario_truth_responsibility",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id", "scenario_truth_id", name="pk_scenario_truth"
        ),
        sa.UniqueConstraint(
            "dataset_version_id",
            "po_line_schedule_id",
            name="uq_scenario_truth_schedule",
        ),
        schema="evaluation",
    )
    op.create_index(
        "ix_scenario_truth_dataset_cause",
        "scenario_truth",
        ["dataset_version_id", "true_cause"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scenario_truth_dataset_cause",
        table_name="scenario_truth",
        schema="evaluation",
    )
    op.drop_table("scenario_truth", schema="evaluation")
