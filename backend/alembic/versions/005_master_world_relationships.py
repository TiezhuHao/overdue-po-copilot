"""Create Phase 2 master-world relationship tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "005_master_world_relationships"
down_revision = "004_master_relationships"
branch_labels = None
depends_on = None


def _identity_columns(entity_name: str) -> list[sa.Column]:
    return [
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(f"{entity_name}_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def _dataset_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["dataset_version_id"],
        ["platform.dataset_versions.dataset_version_id"],
        ondelete="CASCADE",
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "employee_role_assignments",
        *_identity_columns("employee_role_assignment"),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_type", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "role_type IN ('BUYER', 'MATERIAL_CONTROLLER', "
            "'PRIMARY_MATERIAL_CONTROLLER', 'RESEARCH_REPRESENTATIVE')",
            name="ck_employee_role_assignments_role_type",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_employee_role_assignments_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id",
            "employee_role_assignment_id",
            name="pk_employee_role_assignments",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_employee_roles_dataset_employee",
        "employee_role_assignments",
        ["dataset_version_id", "employee_id"],
        schema="platform",
    )

    op.create_table(
        "material_supplier_assignments",
        *_identity_columns("material_supplier_assignment"),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_type", sa.String(length=32), nullable=False),
        sa.Column("agreement_unit_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "supplier_id"],
            ["platform.suppliers.dataset_version_id", "platform.suppliers.supplier_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "assignment_type IN ('PRIMARY', 'ALTERNATE')",
            name="ck_material_supplier_assignments_assignment_type",
        ),
        sa.CheckConstraint(
            "agreement_unit_price IS NULL OR agreement_unit_price >= 0",
            name="ck_material_supplier_assignments_price_nonnegative",
        ),
        sa.CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="ck_material_supplier_assignments_currency_code",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_material_supplier_assignments_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id",
            "material_supplier_assignment_id",
            name="pk_material_supplier_assignments",
        ),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=sa.text("assignment_type = 'PRIMARY'"),
            using="gist",
            name="ex_material_supplier_primary_period",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_material_suppliers_dataset_material",
        "material_supplier_assignments",
        ["dataset_version_id", "material_id"],
        schema="platform",
    )

    op.create_table(
        "project_customers",
        *_identity_columns("project_customer"),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "project_id"],
            ["platform.projects.dataset_version_id", "platform.projects.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "customer_id"],
            ["platform.customers.dataset_version_id", "platform.customers.customer_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "relationship_type IN ('PRIMARY', 'SECONDARY')",
            name="ck_project_customers_relationship_type",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_project_customers_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id", "project_customer_id", name="pk_project_customers"
        ),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="),
            ("project_id", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=sa.text("relationship_type = 'PRIMARY'"),
            using="gist",
            name="ex_project_customer_primary_period",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_project_customers_dataset_project",
        "project_customers",
        ["dataset_version_id", "project_id"],
        schema="platform",
    )

    op.create_table(
        "material_responsibility_assignments",
        *_identity_columns("material_responsibility_assignment"),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("responsibility_type", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "responsibility_type IN ('BUYER', 'MATERIAL_CONTROLLER', "
            "'PRIMARY_MATERIAL_CONTROLLER')",
            name="ck_material_responsibility_assignments_type",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_material_responsibility_assignments_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id",
            "material_responsibility_assignment_id",
            name="pk_material_responsibility_assignments",
        ),
        postgresql.ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            ("organization_id", "="),
            ("responsibility_type", "="),
            (sa.text("daterange(effective_from, effective_to, '[)')"), "&&"),
            using="gist",
            name="ex_material_responsibility_active_period",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_material_responsibilities_dataset_material",
        "material_responsibility_assignments",
        ["dataset_version_id", "material_id"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_responsibilities_dataset_material",
        table_name="material_responsibility_assignments",
        schema="platform",
    )
    op.drop_table("material_responsibility_assignments", schema="platform")
    op.drop_index(
        "ix_project_customers_dataset_project",
        table_name="project_customers",
        schema="platform",
    )
    op.drop_table("project_customers", schema="platform")
    op.drop_index(
        "ix_material_suppliers_dataset_material",
        table_name="material_supplier_assignments",
        schema="platform",
    )
    op.drop_table("material_supplier_assignments", schema="platform")
    op.drop_index(
        "ix_employee_roles_dataset_employee",
        table_name="employee_role_assignments",
        schema="platform",
    )
    op.drop_table("employee_role_assignments", schema="platform")
