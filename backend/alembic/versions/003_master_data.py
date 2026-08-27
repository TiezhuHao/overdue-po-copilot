"""Create Phase 1 master data tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "003_master_data"
down_revision = "002_dataset_versions"
branch_labels = None
depends_on = None


def _dataset_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["dataset_version_id"],
        ["platform.dataset_versions.dataset_version_id"],
        ondelete="CASCADE",
    )


def _identity_columns(entity_name: str) -> list[sa.Column]:
    return [
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(f"{entity_name}_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "organizations",
        *_identity_columns("organization"),
        sa.Column("organization_code", sa.String(length=100), nullable=False),
        sa.Column("organization_name", sa.String(length=300), nullable=False),
        sa.Column("organization_type", sa.String(length=50), nullable=False),
        sa.Column("inventory_organization_type", sa.String(length=50), nullable=True),
        sa.Column("parent_organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "parent_organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "organization_type IN ('INVENTORY_ORG', 'BUSINESS_ENTITY', 'BUSINESS_UNIT', "
            "'PLANNING_DEPARTMENT', 'DEPARTMENT')",
            name="ck_organizations_organization_type",
        ),
        sa.CheckConstraint(
            "inventory_organization_type IS NULL OR inventory_organization_type IN "
            "('TRIAL', 'MASS_PRODUCTION')",
            name="ck_organizations_inventory_organization_type",
        ),
        sa.CheckConstraint(
            "(organization_type = 'INVENTORY_ORG' AND inventory_organization_type IS NOT NULL) OR "
            "(organization_type <> 'INVENTORY_ORG' AND inventory_organization_type IS NULL)",
            name="ck_organizations_inventory_type_scope",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_organizations_organization_effective_period",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id", "organization_id", name="pk_organizations"
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "organization_code", name="uq_organizations_dataset_code"
        ),
        schema="platform",
    )

    op.create_table(
        "employees",
        *_identity_columns("employee"),
        sa.Column("employee_code", sa.String(length=100), nullable=False),
        sa.Column("account_name", sa.String(length=150), nullable=False),
        sa.Column("employee_name", sa.String(length=200), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manager_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("director_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "manager_employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
            name="fk_employees_manager",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "director_employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
            name="fk_employees_director",
        ),
        sa.PrimaryKeyConstraint("dataset_version_id", "employee_id", name="pk_employees"),
        sa.UniqueConstraint(
            "dataset_version_id", "employee_code", name="uq_employees_dataset_code"
        ),
        schema="platform",
    )

    op.create_table(
        "materials",
        *_identity_columns("material"),
        sa.Column("material_code", sa.String(length=100), nullable=False),
        sa.Column("material_description", sa.String(length=500), nullable=True),
        sa.Column("specification_model", sa.String(length=300), nullable=True),
        sa.Column("model", sa.String(length=300), nullable=True),
        sa.Column("material_lt_days", sa.Integer(), nullable=False),
        sa.Column("manufacturer_lt_days", sa.Integer(), nullable=True),
        sa.Column("minimum_pack_qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("minimum_order_qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("non_cancelable_non_returnable_flag", sa.Boolean(), nullable=False),
        sa.Column(
            "primary_inventory_organization_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        _created_at(),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "primary_inventory_organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("material_lt_days >= 0", name="ck_materials_material_lt_nonnegative"),
        sa.CheckConstraint(
            "manufacturer_lt_days IS NULL OR manufacturer_lt_days >= 0",
            name="ck_materials_manufacturer_lt_nonnegative",
        ),
        sa.CheckConstraint("minimum_pack_qty >= 0", name="ck_materials_minimum_pack_nonnegative"),
        sa.CheckConstraint("minimum_order_qty >= 0", name="ck_materials_minimum_order_nonnegative"),
        sa.PrimaryKeyConstraint("dataset_version_id", "material_id", name="pk_materials"),
        sa.UniqueConstraint(
            "dataset_version_id", "material_code", name="uq_materials_dataset_code"
        ),
        schema="platform",
    )

    for table_name, entity_name, code_length in (
        ("projects", "project", 100),
        ("customers", "customer", 100),
        ("suppliers", "supplier", 100),
    ):
        if table_name == "projects":
            extra_columns = [
                sa.Column("project_code", sa.String(code_length), nullable=False),
                sa.Column("project_name", sa.String(300), nullable=False),
                sa.Column("customer_project_name", sa.String(300), nullable=True),
                sa.Column("brand_name", sa.String(200), nullable=True),
                sa.Column("product_type", sa.String(200), nullable=True),
                sa.Column("shipment_type", sa.String(100), nullable=True),
                sa.Column("business_mode", sa.String(100), nullable=True),
            ]
        elif table_name == "customers":
            extra_columns = [
                sa.Column("customer_code", sa.String(code_length), nullable=False),
                sa.Column("customer_short_code", sa.String(100), nullable=True),
                sa.Column("customer_name", sa.String(300), nullable=False),
            ]
        else:
            extra_columns = [
                sa.Column("supplier_code", sa.String(code_length), nullable=False),
                sa.Column("supplier_name", sa.String(300), nullable=False),
                sa.Column("supplier_name_en", sa.String(300), nullable=True),
                sa.Column("currency_code", sa.String(3), nullable=True),
                sa.Column("is_active", sa.Boolean(), nullable=False),
            ]
        constraints: list[sa.SchemaItem] = [
            _created_at(),
            _dataset_fk(),
            sa.PrimaryKeyConstraint(
                "dataset_version_id", f"{entity_name}_id", name=f"pk_{table_name}"
            ),
            sa.UniqueConstraint(
                "dataset_version_id",
                f"{entity_name}_code",
                name=f"uq_{table_name}_dataset_code",
            ),
        ]
        if table_name == "suppliers":
            constraints.append(
                sa.CheckConstraint(
                    "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
                    name="ck_suppliers_currency_code_format",
                )
            )
        op.create_table(
            table_name,
            *_identity_columns(entity_name),
            *extra_columns,
            *constraints,
            schema="platform",
        )


def downgrade() -> None:
    for table_name in ("suppliers", "customers", "projects", "materials", "employees", "organizations"):
        op.drop_table(table_name, schema="platform")
