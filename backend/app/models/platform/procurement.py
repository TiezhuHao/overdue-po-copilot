from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PoHeader(Base):
    __tablename__ = "po_headers"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "po_number"),
        ForeignKeyConstraint(["dataset_version_id"], ["platform.dataset_versions.dataset_version_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "business_entity_id"], ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"], ondelete="RESTRICT", name="fk_po_headers_business_entity"),
        ForeignKeyConstraint(["dataset_version_id", "inventory_organization_id"], ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"], ondelete="RESTRICT", name="fk_po_headers_inventory_organization"),
        ForeignKeyConstraint(["dataset_version_id", "supplier_id"], ["platform.suppliers.dataset_version_id", "platform.suppliers.supplier_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["dataset_version_id", "order_buyer_employee_id"], ["platform.employees.dataset_version_id", "platform.employees.employee_id"], ondelete="RESTRICT"),
        CheckConstraint("po_status IN ('OPEN', 'PARTIALLY_RECEIVED', 'CLOSED', 'CANCELLED')", name="po_header_status"),
        CheckConstraint("close_status IN ('OPEN', 'CLOSED')", name="po_header_close_status"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_header_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_number: Mapped[str] = mapped_column(String(100), nullable=False)
    business_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    inventory_organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    order_buyer_employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    po_status: Mapped[str] = mapped_column(String(32), nullable=False)
    close_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PoLine(Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "po_header_id", "po_line_number"),
        ForeignKeyConstraint(["dataset_version_id"], ["platform.dataset_versions.dataset_version_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "po_header_id"], ["platform.po_headers.dataset_version_id", "platform.po_headers.po_header_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "material_id"], ["platform.materials.dataset_version_id", "platform.materials.material_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["dataset_version_id", "po_reference_project_id"], ["platform.projects.dataset_version_id", "platform.projects.project_id"], ondelete="RESTRICT"),
        CheckConstraint("po_line_number > 0", name="po_line_number_positive"),
        CheckConstraint("ordered_qty >= 0", name="po_line_ordered_nonnegative"),
        CheckConstraint("received_qty >= 0", name="po_line_received_nonnegative"),
        CheckConstraint("received_qty <= ordered_qty", name="po_line_received_within_ordered"),
        CheckConstraint("material_lt_days_at_order >= 0", name="po_line_lt_nonnegative"),
        CheckConstraint("line_status IN ('OPEN', 'PARTIALLY_RECEIVED', 'CLOSED', 'CANCELLED')", name="po_line_status"),
        Index("ix_po_lines_dataset_material", "dataset_version_id", "material_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_header_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    po_line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    po_reference_project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    ordered_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    received_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    material_lt_days_at_order: Mapped[int] = mapped_column(Integer, nullable=False)
    can_close: Mapped[bool] = mapped_column(Boolean, nullable=False)
    completion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    line_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PoLineSchedule(Base):
    __tablename__ = "po_line_schedules"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "po_line_id", "shipment_number"),
        ForeignKeyConstraint(["dataset_version_id"], ["platform.dataset_versions.dataset_version_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "po_line_id"], ["platform.po_lines.dataset_version_id", "platform.po_lines.po_line_id"], ondelete="CASCADE"),
        CheckConstraint("shipment_number > 0", name="po_schedule_number_positive"),
        CheckConstraint("schedule_qty >= 0", name="po_schedule_qty_nonnegative"),
        CheckConstraint("schedule_received_qty >= 0", name="po_schedule_received_nonnegative"),
        CheckConstraint("schedule_received_qty <= schedule_qty", name="po_schedule_received_within_qty"),
        CheckConstraint("close_status IN ('OPEN', 'CLOSED')", name="po_schedule_close_status"),
        Index("ix_po_schedules_dataset_line", "dataset_version_id", "po_line_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_line_schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    shipment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schedule_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    schedule_received_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
