"""Create Phase 1 master data relationships."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "004_master_relationships"
down_revision = "003_master_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_projects",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relationship_type", sa.String(length=100), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "project_id"],
            ["platform.projects.dataset_version_id", "platform.projects.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_material_projects_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id", "material_project_id", name="pk_material_projects"
        ),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            ("project_id", "="),
            ("organization_id", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=sa.text("organization_id IS NOT NULL"),
            using="gist",
            name="ex_material_project_period_with_org",
        ),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            ("project_id", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=sa.text("organization_id IS NULL"),
            using="gist",
            name="ex_material_project_period_without_org",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_material_projects_dataset_material",
        "material_projects",
        ["dataset_version_id", "material_id"],
        schema="platform",
    )

    op.create_table(
        "material_mpm_assignments",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_mpm_assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_material_mpm_assignments_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id",
            "material_mpm_assignment_id",
            name="pk_material_mpm_assignments",
        ),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            using="gist",
            name="ex_material_mpm_active_period",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_material_mpm_dataset_material",
        "material_mpm_assignments",
        ["dataset_version_id", "material_id"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_mpm_dataset_material",
        table_name="material_mpm_assignments",
        schema="platform",
    )
    op.drop_table("material_mpm_assignments", schema="platform")
    op.drop_index(
        "ix_material_projects_dataset_material",
        table_name="material_projects",
        schema="platform",
    )
    op.drop_table("material_projects", schema="platform")
