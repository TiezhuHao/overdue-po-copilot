from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmployeeRoleAssignment(Base):
    __tablename__ = "employee_role_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "role_type IN ('BUYER', 'MATERIAL_CONTROLLER', "
            "'PRIMARY_MATERIAL_CONTROLLER', 'RESEARCH_REPRESENTATIVE')",
            name="employee_role_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="employee_role_effective_period",
        ),
        Index("ix_employee_roles_dataset_employee", "dataset_version_id", "employee_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    employee_role_assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    role_type: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MaterialSupplierAssignment(Base):
    __tablename__ = "material_supplier_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "supplier_id"],
            ["platform.suppliers.dataset_version_id", "platform.suppliers.supplier_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "assignment_type IN ('PRIMARY', 'ALTERNATE')",
            name="material_supplier_assignment_type",
        ),
        CheckConstraint(
            "agreement_unit_price IS NULL OR agreement_unit_price >= 0",
            name="material_supplier_price_nonnegative",
        ),
        CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="material_supplier_currency_code",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="material_supplier_effective_period",
        ),
        ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=text("assignment_type = 'PRIMARY'"),
            using="gist",
            name="ex_material_supplier_primary_period",
        ),
        Index("ix_material_suppliers_dataset_material", "dataset_version_id", "material_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_supplier_assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    agreement_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjectCustomer(Base):
    __tablename__ = "project_customers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "project_id"],
            ["platform.projects.dataset_version_id", "platform.projects.project_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "customer_id"],
            ["platform.customers.dataset_version_id", "platform.customers.customer_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "relationship_type IN ('PRIMARY', 'SECONDARY')",
            name="project_customer_relationship_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="project_customer_effective_period",
        ),
        ExcludeConstraint(
            ("dataset_version_id", "="),
            ("project_id", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=text("relationship_type = 'PRIMARY'"),
            using="gist",
            name="ex_project_customer_primary_period",
        ),
        Index("ix_project_customers_dataset_project", "dataset_version_id", "project_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MaterialResponsibilityAssignment(Base):
    __tablename__ = "material_responsibility_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "material_id"],
            ["platform.materials.dataset_version_id", "platform.materials.material_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "responsibility_type IN ('BUYER', 'MATERIAL_CONTROLLER', "
            "'PRIMARY_MATERIAL_CONTROLLER')",
            name="material_responsibility_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="material_responsibility_effective_period",
        ),
        ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            ("organization_id", "="),
            ("responsibility_type", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            using="gist",
            name="ex_material_responsibility_active_period",
        ),
        Index(
            "ix_material_responsibilities_dataset_material",
            "dataset_version_id",
            "material_id",
        ),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_responsibility_assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    responsibility_type: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
