from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "supplier_code"),
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'",
            name="currency_code_format",
        ),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    supplier_code: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(300), nullable=False)
    supplier_name_en: Mapped[str | None] = mapped_column(String(300), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
