from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.datasets import DatasetListResponse, DatasetResponse
from app.services.report_queries import ReportQueryService


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=DatasetListResponse)
def list_datasets(session: Annotated[Session, Depends(get_db_session)]):
    rows = ReportQueryService(session).list_datasets()
    return DatasetListResponse(items=[DatasetResponse.model_validate(row) for row in rows], total=len(rows))


@router.get("/{dataset_version_id}", response_model=DatasetResponse)
def get_dataset(dataset_version_id: UUID, session: Annotated[Session, Depends(get_db_session)]):
    row = ReportQueryService(session).get_dataset(dataset_version_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "DATASET_NOT_FOUND"})
    return DatasetResponse.model_validate(row)

