"""Business lifecycle, configuration and dated demand observations (no diagnostics)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Numeric, PrimaryKeyConstraint, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _dataset_fk():
    return ForeignKeyConstraint(["dataset_version_id"], ["platform.dataset_versions.dataset_version_id"], ondelete="CASCADE")


def _fk(column, table, target=None, ondelete="RESTRICT"):
    return ForeignKeyConstraint(
        ["dataset_version_id", column],
        [f"platform.{table}.dataset_version_id", f"platform.{table}.{target or column}"],
        ondelete=ondelete, name=f"fk_evidence_{column}_{table}",
    )


class EvidenceRow:
    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectLifecycleHistory(EvidenceRow, Base):
    __tablename__ = "project_lifecycle_history"
    __table_args__ = (
        PrimaryKeyConstraint("dataset_version_id", "project_lifecycle_id"),
        _dataset_fk(), _fk("project_id", "projects", ondelete="CASCADE"),
        CheckConstraint("lifecycle_stage IN ('NPI', 'MASS_PRODUCTION', 'EOL')", name="lifecycle_stage"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="lifecycle_period"),
        ExcludeConstraint(
            ("dataset_version_id", "="), ("project_id", "="),
            (text("daterange(effective_from, effective_to, '[)')"), "&&"),
            using="gist", name="ex_project_lifecycle_period",
        ),
        Index("ix_lifecycle_project_period", "dataset_version_id", "project_id", "effective_from", "effective_to"),
        {"schema": "platform"},
    )
    project_lifecycle_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lifecycle_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class ProductConfig(EvidenceRow, Base):
    __tablename__ = "product_configs"
    __table_args__ = (
        PrimaryKeyConstraint("dataset_version_id", "product_config_id"),
        _dataset_fk(), _fk("project_id", "projects", ondelete="CASCADE"),
        _fk("customer_id", "customers"),
        _fk("business_unit_id", "organizations", "organization_id"),
        _fk("planning_department_id", "organizations", "organization_id"),
        _fk("research_representative_employee_id", "employees", "employee_id"),
        _fk("modified_by_employee_id", "employees", "employee_id"),
        UniqueConstraint("dataset_version_id", "product_config_name", "config_version"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="product_config_period"),
        CheckConstraint("product_config_status IN ('ACTIVE', 'INACTIVE')", name="product_config_status"),
        *(Index(f"ix_product_config_{field}", "dataset_version_id", field) for field in (
            "project_id", "customer_id", "business_unit_id", "planning_department_id",
            "research_representative_employee_id", "modified_by_employee_id",
        )),
        {"schema": "platform"},
    )
    product_config_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_config_type: Mapped[str] = mapped_column(String(64), nullable=False)
    product_config_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_version: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_material_code: Mapped[str | None] = mapped_column(String(100))
    business_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    planning_department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    research_representative_employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_config_status: Mapped[str] = mapped_column(String(32), nullable=False)
    product_category_level_1: Mapped[str] = mapped_column(String(100), nullable=False)
    product_category_level_2: Mapped[str] = mapped_column(String(100), nullable=False)
    product_category_level_3: Mapped[str] = mapped_column(String(100), nullable=False)
    product_team_name: Mapped[str] = mapped_column(String(100), nullable=False)
    modified_by_employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class ProductConfigMaterial(EvidenceRow, Base):
    __tablename__ = "product_config_materials"
    __table_args__ = (
        PrimaryKeyConstraint("dataset_version_id", "product_config_material_id"),
        _dataset_fk(), _fk("product_config_id", "product_configs", ondelete="CASCADE"),
        _fk("material_id", "materials"),
        UniqueConstraint("dataset_version_id", "product_config_id", "material_id"),
        Index("ix_config_material_material", "dataset_version_id", "material_id"),
        {"schema": "platform"},
    )
    product_config_material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    product_config_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class DemandSignal(EvidenceRow, Base):
    __tablename__ = "demand_signals"
    __table_args__ = (
        PrimaryKeyConstraint("dataset_version_id", "demand_signal_id"),
        _dataset_fk(), _fk("material_id", "materials"), _fk("project_id", "projects"),
        _fk("organization_id", "organizations"),
        UniqueConstraint("dataset_version_id", "material_id", "project_id"),
        CheckConstraint("signal_kind = 'PLANNED_DEMAND'", name="signal_kind"),
        CheckConstraint("reference_daily_qty > 0", name="reference_daily_qty"),
        CheckConstraint("scenario_generation_key ~ '^[a-f0-9]{64}$'", name="opaque_generation_key"),
        Index("ix_demand_signal_project", "dataset_version_id", "project_id"),
        Index("ix_demand_signal_organization", "dataset_version_id", "organization_id"),
        {"schema": "platform"},
    )
    demand_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    signal_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_from: Mapped[date] = mapped_column(Date, nullable=False)
    reference_daily_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class DemandSignalPoint(EvidenceRow, Base):
    __tablename__ = "demand_signal_points"
    __table_args__ = (
        PrimaryKeyConstraint("dataset_version_id", "demand_signal_point_id"),
        _dataset_fk(), _fk("demand_signal_id", "demand_signals", ondelete="CASCADE"),
        UniqueConstraint("dataset_version_id", "demand_signal_id", "demand_date"),
        CheckConstraint("demand_qty >= 0", name="demand_qty"),
        Index("ix_demand_point_date", "dataset_version_id", "demand_date"),
        {"schema": "platform"},
    )
    demand_signal_point_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    demand_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    demand_date: Mapped[date] = mapped_column(Date, nullable=False)
    demand_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class DemandSignalRevision(EvidenceRow, Base):
    """A source observation replaces a day's planned quantity; not a forecast version."""

    __tablename__ = "demand_signal_revisions"
    __table_args__ = (
        PrimaryKeyConstraint("dataset_version_id", "demand_signal_revision_id"),
        _dataset_fk(),
        ForeignKeyConstraint(
            ["dataset_version_id", "demand_signal_id", "demand_date"],
            [f"platform.demand_signal_points.{field}" for field in ("dataset_version_id", "demand_signal_id", "demand_date")],
            ondelete="CASCADE",
        ),
        UniqueConstraint("dataset_version_id", "demand_signal_id", "observed_on", "demand_date"),
        CheckConstraint("demand_qty >= 0", name="revision_demand_qty"),
        Index("ix_demand_revision_point", "dataset_version_id", "demand_signal_id", "demand_date"),
        {"schema": "platform"},
    )
    demand_signal_revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    demand_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    demand_date: Mapped[date] = mapped_column(Date, nullable=False)
    demand_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


EVIDENCE_MODELS = (
    ProjectLifecycleHistory, ProductConfig, ProductConfigMaterial,
    DemandSignal, DemandSignalPoint, DemandSignalRevision,
)
