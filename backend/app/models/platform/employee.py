from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "employee_code"),
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "manager_employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
            name="fk_employees_manager",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "director_employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
            name="fk_employees_director",
        ),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    manager_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    director_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
