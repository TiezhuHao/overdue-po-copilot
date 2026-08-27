from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "organization_code"),
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "parent_organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "organization_type IN ('INVENTORY_ORG', 'BUSINESS_ENTITY', 'BUSINESS_UNIT', "
            "'PLANNING_DEPARTMENT', 'DEPARTMENT')",
            name="organization_type",
        ),
        CheckConstraint(
            "inventory_organization_type IS NULL OR "
            "inventory_organization_type IN ('TRIAL', 'MASS_PRODUCTION')",
            name="inventory_organization_type",
        ),
        CheckConstraint(
            "(organization_type = 'INVENTORY_ORG' AND inventory_organization_type IS NOT NULL) OR "
            "(organization_type <> 'INVENTORY_ORG' AND inventory_organization_type IS NULL)",
            name="inventory_type_scope",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="organization_effective_period",
        ),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_code: Mapped[str] = mapped_column(String(100), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(300), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(50), nullable=False)
    inventory_organization_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
