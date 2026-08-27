from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "material_code"),
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "primary_inventory_organization_id"],
            ["platform.organizations.dataset_version_id", "platform.organizations.organization_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("material_lt_days >= 0", name="material_lt_nonnegative"),
        CheckConstraint(
            "manufacturer_lt_days IS NULL OR manufacturer_lt_days >= 0",
            name="manufacturer_lt_nonnegative",
        ),
        CheckConstraint("minimum_pack_qty >= 0", name="minimum_pack_nonnegative"),
        CheckConstraint("minimum_order_qty >= 0", name="minimum_order_nonnegative"),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    material_code: Mapped[str] = mapped_column(String(100), nullable=False)
    material_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    specification_model: Mapped[str | None] = mapped_column(String(300), nullable=True)
    model: Mapped[str | None] = mapped_column(String(300), nullable=True)
    material_lt_days: Mapped[int] = mapped_column(Integer, nullable=False)
    manufacturer_lt_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_pack_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    minimum_order_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    non_cancelable_non_returnable_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    primary_inventory_organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
