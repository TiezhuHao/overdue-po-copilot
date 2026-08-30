from typing import Annotated
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.reports import (
    Report1Page, Report2Page, Report3Page, Report4Page, Report5Page, Report6Page,
)
from app.services.report_queries import ReportQueryError, ReportQueryService


router = APIRouter(prefix="/reports", tags=["reports"])
Db = Annotated[Session, Depends(get_db_session)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=500)]


def _run(session, report_id, response_model, page, page_size, dataset_version_id, dataset_version_name, filters):
    service = ReportQueryService(session)
    try:
        dataset = service.select_dataset(dataset_version_id, dataset_version_name)
        if report_id == 6:
            total, rows = service.report6_page(dataset, page, page_size, filters)
        else:
            total, rows = service.page(report_id, dataset, page, page_size, filters)
    except ReportQueryError as exc:
        code = str(exc)
        status = 404 if code in {"NO_READY_DATASET", "DATASET_NOT_FOUND"} else 422
        raise HTTPException(status_code=status, detail={"code": code}) from exc
    extra = {"stockpile_selection": getattr(service, "stockpile_selection", None)} if report_id == 6 else {}
    return response_model(dataset_version_id=dataset.dataset_version_id, snapshot_date=dataset.snapshot_date,
                          page=page, page_size=page_size, total=total, items=rows, **extra)


@router.get("/overdue-pos", response_model=Report1Page)
def report1(session: Db, page: Page = 1, page_size: PageSize = 100, dataset_version_id: UUID | None = None,
            dataset_version_name: str | None = None, material_code: str | None = None,
            supplier: str | None = None, buyer: str | None = None, project: str | None = None,
            po_number: str | None = None, material_id: UUID | None = None,
            po_header_id: UUID | None = None, po_line_id: UUID | None = None,
            po_line_schedule_id: UUID | None = None, po_reference_project_id: UUID | None = None):
    return _run(session, 1, Report1Page, page, page_size, dataset_version_id, dataset_version_name, locals())


@router.get("/material-supply-demand", response_model=Report2Page)
def report2(session: Db, page: Page = 1, page_size: PageSize = 100, dataset_version_id: UUID | None = None,
            dataset_version_name: str | None = None, material_code: str | None = None,
            mpm: str | None = None, surplus_sign: str | None = None, material_id: UUID | None = None):
    return _run(session, 2, Report2Page, page, page_size, dataset_version_id, dataset_version_name, locals())


@router.get("/forecast-history", response_model=Report3Page)
def report3(session: Db, page: Page = 1, page_size: PageSize = 100, dataset_version_id: UUID | None = None,
            dataset_version_name: str | None = None, po_number: str | None = None,
            material_code: str | None = None, project: str | None = None,
            forecast_version: str | None = None, window_role: str | None = None,
            material_id: UUID | None = None, project_id: UUID | None = None,
            po_line_schedule_id: UUID | None = None, forecast_version_id: UUID | None = None):
    return _run(session, 3, Report3Page, page, page_size, dataset_version_id, dataset_version_name, locals())


@router.get("/latest-13w-forecast", response_model=Report4Page)
def report4(session: Db, page: Page = 1, page_size: PageSize = 100, dataset_version_id: UUID | None = None,
            dataset_version_name: str | None = None, material_code: str | None = None,
            material_id: UUID | None = None):
    return _run(session, 4, Report4Page, page, page_size, dataset_version_id, dataset_version_name, locals())


@router.get("/product-configurations", response_model=Report5Page)
def report5(session: Db, page: Page = 1, page_size: PageSize = 100, dataset_version_id: UUID | None = None,
            dataset_version_name: str | None = None, project: str | None = None,
            material_code: str | None = None, business_unit: str | None = None,
            planning_department: str | None = None, lifecycle: str | None = None,
            material_id: UUID | None = None, project_id: UUID | None = None):
    return _run(session, 5, Report5Page, page, page_size, dataset_version_id, dataset_version_name, locals())


@router.get("/stockpile", response_model=Report6Page)
def report6(session: Db, page: Page = 1, page_size: PageSize = 100, dataset_version_id: UUID | None = None,
            dataset_version_name: str | None = None, material_code: str | None = None,
            material_id: UUID | None = None, as_of_date: date | None = None,
            stockpile_version_id: UUID | None = None):
    return _run(session, 6, Report6Page, page, page_size, dataset_version_id, dataset_version_name, locals())
