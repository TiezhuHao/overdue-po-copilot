from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "project_code"),
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["platform.dataset_versions.dataset_version_id"],
            ondelete="CASCADE",
        ),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_code: Mapped[str] = mapped_column(String(100), nullable=False)
    project_name: Mapped[str] = mapped_column(String(300), nullable=False)
    customer_project_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    shipment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_mode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
