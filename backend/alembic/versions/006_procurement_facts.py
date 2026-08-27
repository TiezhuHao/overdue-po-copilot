"""Create Phase 3 procurement fact tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "006_procurement_facts"
down_revision = "005_master_world_relationships"
branch_labels = None
depends_on = None


def _dataset_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["dataset_version_id"],
        ["platform.dataset_versions.dataset_version_id"],
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "po_headers",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_header_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_number", sa.String(100), nullable=False),
        sa.Column("business_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_buyer_employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_status", sa.String(32), nullable=False),
        sa.Column("close_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "business_entity_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
            name="fk_po_headers_business_entity",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "inventory_organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
            name="fk_po_headers_inventory_organization",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "supplier_id"],
            ["platform.suppliers.dataset_version_id", "platform.suppliers.supplier_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "order_buyer_employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "po_status IN ('OPEN', 'PARTIALLY_RECEIVED', 'CLOSED', 'CANCELLED')",
            name="ck_po_headers_status",
        ),
        sa.CheckConstraint(
            "close_status IN ('OPEN', 'CLOSED')",
            name="ck_po_headers_close_status",
        ),
        sa.PrimaryKeyConstraint("dataset_version_id", "po_header_id", name="pk_po_headers"),
        sa.UniqueConstraint("dataset_version_id", "po_number", name="uq_po_headers_number"),
        schema="platform",
    )

    op.create_table(
        "po_lines",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_header_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_line_number", sa.Integer(), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_reference_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ordered_qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("received_qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("material_lt_days_at_order", sa.Integer(), nullable=False),
        sa.Column("can_close", sa.Boolean(), nullable=False),
        sa.Column("completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("line_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "po_header_id"],
            ["platform.po_headers.dataset_version_id", "platform.po_headers.po_header_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "po_reference_project_id"],
            ["platform.projects.dataset_version_id", "platform.projects.project_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("po_line_number > 0", name="ck_po_lines_number_positive"),
        sa.CheckConstraint("ordered_qty >= 0", name="ck_po_lines_ordered_nonnegative"),
        sa.CheckConstraint("received_qty >= 0", name="ck_po_lines_received_nonnegative"),
        sa.CheckConstraint("received_qty <= ordered_qty", name="ck_po_lines_received_within_ordered"),
        sa.CheckConstraint("material_lt_days_at_order >= 0", name="ck_po_lines_lt_nonnegative"),
        sa.CheckConstraint(
            "line_status IN ('OPEN', 'PARTIALLY_RECEIVED', 'CLOSED', 'CANCELLED')",
            name="ck_po_lines_status",
        ),
        sa.PrimaryKeyConstraint("dataset_version_id", "po_line_id", name="pk_po_lines"),
        sa.UniqueConstraint(
            "dataset_version_id", "po_header_id", "po_line_number", name="uq_po_lines_header_number"
        ),
        schema="platform",
    )
    op.create_index(
        "ix_po_lines_dataset_material", "po_lines", ["dataset_version_id", "material_id"], schema="platform"
    )

    op.create_table(
        "po_line_schedules",
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_line_schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipment_number", sa.Integer(), nullable=False),
        sa.Column("schedule_qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("schedule_received_qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("close_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        _dataset_fk(),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "po_line_id"],
            ["platform.po_lines.dataset_version_id", "platform.po_lines.po_line_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("shipment_number > 0", name="ck_po_line_schedules_number_positive"),
        sa.CheckConstraint("schedule_qty >= 0", name="ck_po_line_schedules_qty_nonnegative"),
        sa.CheckConstraint(
            "schedule_received_qty >= 0", name="ck_po_line_schedules_received_nonnegative"
        ),
        sa.CheckConstraint(
            "schedule_received_qty <= schedule_qty", name="ck_po_line_schedules_received_within_qty"
        ),
        sa.CheckConstraint(
            "close_status IN ('OPEN', 'CLOSED')", name="ck_po_line_schedules_close_status"
        ),
        sa.PrimaryKeyConstraint(
            "dataset_version_id", "po_line_schedule_id", name="pk_po_line_schedules"
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "po_line_id", "shipment_number", name="uq_po_line_schedules_shipment"
        ),
        schema="platform",
    )
    op.create_index(
        "ix_po_schedules_dataset_line",
        "po_line_schedules",
        ["dataset_version_id", "po_line_id"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index("ix_po_schedules_dataset_line", table_name="po_line_schedules", schema="platform")
    op.drop_table("po_line_schedules", schema="platform")
    op.drop_index("ix_po_lines_dataset_material", table_name="po_lines", schema="platform")
    op.drop_table("po_lines", schema="platform")
    op.drop_table("po_headers", schema="platform")
