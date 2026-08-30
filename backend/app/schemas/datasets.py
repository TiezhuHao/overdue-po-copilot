from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_version_id: UUID
    dataset_version_name: str
    snapshot_date: date
    status: str
    generation_signature: str
    business_content_hash: str | None


class DatasetListResponse(BaseModel):
    items: list[DatasetResponse]
    total: int

