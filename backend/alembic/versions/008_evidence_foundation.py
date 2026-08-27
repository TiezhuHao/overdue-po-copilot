"""Create lifecycle, configuration and shared daily demand evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_evidence_foundation"
down_revision = "007_scenario_truth"
branch_labels = None
depends_on = None


def _uuid(name, nullable=False):
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _fk(column, table, target=None, ondelete="RESTRICT"):
    return sa.ForeignKeyConstraint(
        ["dataset_version_id", column],
        [f"platform.{table}.dataset_version_id", f"platform.{table}.{target or column}"],
        ondelete=ondelete, name=f"fk_evidence_{column}_{table}",
    )


def _create(name, key, *items):
    op.create_table(
        name, _uuid("dataset_version_id"), _uuid(key), *items,
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("dataset_version_id", key),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["platform.dataset_versions.dataset_version_id"], ondelete="CASCADE"),
        schema="platform",
    )


def upgrade():
    _create(
        "project_lifecycle_history", "project_lifecycle_id", _uuid("project_id"),
        sa.Column("lifecycle_stage", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False), sa.Column("effective_to", sa.Date),
        _fk("project_id", "projects", ondelete="CASCADE"),
        sa.CheckConstraint("lifecycle_stage IN ('NPI', 'MASS_PRODUCTION', 'EOL')", name="lifecycle_stage"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="lifecycle_period"),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="), ("project_id", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            using="gist", name="ex_project_lifecycle_period",
        ),
    )
    op.create_index("ix_lifecycle_project_period", "project_lifecycle_history", ["dataset_version_id", "project_id", "effective_from", "effective_to"], schema="platform")
    _create(
        "product_configs", "product_config_id", _uuid("project_id"), _uuid("customer_id"),
        _uuid("business_unit_id"), _uuid("planning_department_id"),
        _uuid("research_representative_employee_id"), _uuid("modified_by_employee_id"),
        *(sa.Column(field, sa.String(size), nullable=False) for field, size in (
            ("product_config_type", 64), ("product_config_name", 200), ("product_name", 200),
            ("config_version", 32), ("product_config_status", 32),
            ("product_category_level_1", 100), ("product_category_level_2", 100),
            ("product_category_level_3", 100), ("product_team_name", 100),
        )),
        sa.Column("customer_material_code", sa.String(100)),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False), sa.Column("effective_to", sa.Date),
        _fk("project_id", "projects", ondelete="CASCADE"), _fk("customer_id", "customers"),
        _fk("business_unit_id", "organizations", "organization_id"),
        _fk("planning_department_id", "organizations", "organization_id"),
        _fk("research_representative_employee_id", "employees", "employee_id"),
        _fk("modified_by_employee_id", "employees", "employee_id"),
        sa.UniqueConstraint("dataset_version_id", "product_config_name", "config_version"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="product_config_period"),
        sa.CheckConstraint("product_config_status IN ('ACTIVE', 'INACTIVE')", name="product_config_status"),
    )
    for field in ("project_id", "customer_id", "business_unit_id", "planning_department_id", "research_representative_employee_id", "modified_by_employee_id"):
        op.create_index(f"ix_product_config_{field}", "product_configs", ["dataset_version_id", field], schema="platform")
    _create(
        "product_config_materials", "product_config_material_id", _uuid("product_config_id"), _uuid("material_id"),
        _fk("product_config_id", "product_configs", ondelete="CASCADE"), _fk("material_id", "materials"),
        sa.UniqueConstraint("dataset_version_id", "product_config_id", "material_id"),
    )
    op.create_index("ix_config_material_material", "product_config_materials", ["dataset_version_id", "material_id"], schema="platform")
    _create(
        "demand_signals", "demand_signal_id", _uuid("material_id"), _uuid("project_id"), _uuid("organization_id", True),
        sa.Column("signal_kind", sa.String(64), nullable=False),
        sa.Column("scenario_generation_key", sa.String(64), nullable=False),
        sa.Column("observed_from", sa.Date, nullable=False),
        sa.Column("reference_daily_qty", sa.Numeric(20, 4), nullable=False),
        _fk("material_id", "materials"), _fk("project_id", "projects"), _fk("organization_id", "organizations"),
        sa.UniqueConstraint("dataset_version_id", "material_id", "project_id"),
        sa.CheckConstraint("signal_kind = 'PLANNED_DEMAND'", name="signal_kind"),
        sa.CheckConstraint("reference_daily_qty > 0", name="reference_daily_qty"),
        sa.CheckConstraint("scenario_generation_key ~ '^[a-f0-9]{64}$'", name="opaque_generation_key"),
    )
    op.create_index("ix_demand_signal_project", "demand_signals", ["dataset_version_id", "project_id"], schema="platform")
    op.create_index("ix_demand_signal_organization", "demand_signals", ["dataset_version_id", "organization_id"], schema="platform")
    _create(
        "demand_signal_points", "demand_signal_point_id", _uuid("demand_signal_id"),
        sa.Column("demand_date", sa.Date, nullable=False), sa.Column("demand_qty", sa.Numeric(20, 4), nullable=False),
        _fk("demand_signal_id", "demand_signals", ondelete="CASCADE"),
        sa.UniqueConstraint("dataset_version_id", "demand_signal_id", "demand_date"),
        sa.CheckConstraint("demand_qty >= 0", name="demand_qty"),
    )
    op.create_index("ix_demand_point_date", "demand_signal_points", ["dataset_version_id", "demand_date"], schema="platform")
    _create(
        "demand_signal_revisions", "demand_signal_revision_id", _uuid("demand_signal_id"),
        sa.Column("observed_on", sa.Date, nullable=False), sa.Column("demand_date", sa.Date, nullable=False),
        sa.Column("demand_qty", sa.Numeric(20, 4), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "demand_signal_id", "demand_date"],
            [f"platform.demand_signal_points.{field}" for field in ("dataset_version_id", "demand_signal_id", "demand_date")],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("dataset_version_id", "demand_signal_id", "observed_on", "demand_date"),
        sa.CheckConstraint("demand_qty >= 0", name="revision_demand_qty"),
    )
    op.create_index("ix_demand_revision_point", "demand_signal_revisions", ["dataset_version_id", "demand_signal_id", "demand_date"], schema="platform")


def downgrade():
    for name in ("demand_signal_revisions", "demand_signal_points", "demand_signals", "product_config_materials", "product_configs", "project_lifecycle_history"):
        op.drop_table(name, schema="platform")
