from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, String, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MaterialProject(Base):
    __tablename__ = "material_projects"
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
            ["dataset_version_id", "project_id"],
            ["platform.projects.dataset_version_id", "platform.projects.project_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="material_project_effective_period",
        ),
        ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            ("project_id", "="),
            ("organization_id", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=text("organization_id IS NOT NULL"),
            name="ex_material_project_period_with_org",
            using="gist",
        ),
        ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            ("project_id", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            where=text("organization_id IS NULL"),
            name="ex_material_project_period_without_org",
            using="gist",
        ),
        Index("ix_material_projects_dataset_material", "dataset_version_id", "material_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    relationship_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MaterialMpmAssignment(Base):
    __tablename__ = "material_mpm_assignments"
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
            ["dataset_version_id", "employee_id"],
            ["platform.employees.dataset_version_id", "platform.employees.employee_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="material_mpm_effective_period",
        ),
        ExcludeConstraint(
            ("dataset_version_id", "="),
            ("material_id", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            name="ex_material_mpm_active_period",
            using="gist",
        ),
        Index("ix_material_mpm_dataset_material", "dataset_version_id", "material_id"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_mpm_assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
