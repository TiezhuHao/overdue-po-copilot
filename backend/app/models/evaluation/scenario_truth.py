from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScenarioTruth(Base):
    __tablename__ = "scenario_truth"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "po_line_schedule_id"),
        ForeignKeyConstraint(["dataset_version_id"], ["platform.dataset_versions.dataset_version_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "po_line_schedule_id"], ["platform.po_line_schedules.dataset_version_id", "platform.po_line_schedules.po_line_schedule_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "po_line_id"], ["platform.po_lines.dataset_version_id", "platform.po_lines.po_line_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["dataset_version_id", "causal_project_id"], ["platform.projects.dataset_version_id", "platform.projects.project_id"], ondelete="RESTRICT"),
        CheckConstraint("scenario_pattern IN ('TRIAL', 'DEMAND_REDUCTION', 'DEMAND_DELAY', 'DEMAND_MIXED', 'CUSTOMER_SIDE_PROJECT_OBSOLESCENCE', 'AFTER_SALES', 'STOCKPILE', 'INTERNAL_SIDE_PROJECT_OBSOLESCENCE')", name="scenario_truth_pattern"),
        CheckConstraint("true_cause IN ('TRIAL', 'STOCKPILE', 'DEMAND_ADJUSTMENT', 'AFTER_SALES', 'PROJECT_OBSOLESCENCE')", name="scenario_truth_cause"),
        CheckConstraint("true_cause_subtype IN ('REDUCTION', 'DELAY', 'MIXED', 'NONE')", name="scenario_truth_subtype"),
        CheckConstraint("demand_change_type IN ('REDUCTION', 'DELAY', 'MIXED', 'NONE')", name="scenario_truth_demand_change"),
        CheckConstraint("lifecycle_state IN ('NPI', 'MASS_PRODUCTION', 'EOL')", name="scenario_truth_lifecycle"),
        CheckConstraint("responsibility_type IS NULL OR responsibility_type IN ('CUSTOMER_SIDE', 'INTERNAL_SIDE', 'MPM')", name="scenario_truth_responsibility"),
        Index("ix_scenario_truth_dataset_cause", "dataset_version_id", "true_cause"),
        {"schema": "evaluation"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    scenario_truth_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    po_line_schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    po_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scenario_pattern: Mapped[str] = mapped_column(String(80), nullable=False)
    true_cause: Mapped[str] = mapped_column(String(64), nullable=False)
    true_cause_subtype: Mapped[str] = mapped_column(String(32), nullable=False)
    causal_project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    demand_change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    stockpile_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    responsibility_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expected_action: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
