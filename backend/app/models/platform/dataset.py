from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('GENERATING', 'READY', 'FAILED', 'RETIRED')",
            name="dataset_status",
        ),
        {"schema": "platform"},
    )

    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    version_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generation_signature: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    business_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
