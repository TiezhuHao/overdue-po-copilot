from datetime import date
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, create_model

from app.reporting.report_header_manifest import get_report_manifest


class TemporalQuantity(BaseModel):
    period: date
    quantity: Any


class AgeQuantity(BaseModel):
    threshold_days: int
    quantity: Any


class ReportPageBase(BaseModel):
    dataset_version_id: UUID
    snapshot_date: date
    page: int
    page_size: int
    total: int


T = TypeVar("T", bound=BaseModel)


class ReportPage(ReportPageBase, Generic[T]):
    items: list[T]


def _item_model(report_id: int, *, normalized_dynamic: bool = False) -> type[BaseModel]:
    fields: dict[str, tuple[Any, Any]] = {}
    for column in get_report_manifest(report_id)["columns"]:
        if column["slot"] and report_id in {3, 6}:
            continue
        fields[column["canonical_field"]] = (Any | None, None)
    if normalized_dynamic and report_id == 3:
        fields.update({
            "po_line_schedule_id": (UUID, ...),
            "forecast_month": (date, ...),
            "forecast_qty": (Any, ...),
            "window_role": (str, ...),
        })
    if normalized_dynamic and report_id == 6:
        fields["future_months"] = (list[TemporalQuantity], ...)
        fields["inventory_age_quantities"] = (list[AgeQuantity], ...)
    return create_model(
        f"Report{report_id}Item",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


Report1Item = _item_model(1)
Report2Item = _item_model(2)
Report3Item = _item_model(3, normalized_dynamic=True)
Report4Item = _item_model(4)
Report5Item = _item_model(5)
Report6Item = _item_model(6, normalized_dynamic=True)

Report1Page = ReportPage[Report1Item]
Report2Page = ReportPage[Report2Item]
Report3Page = ReportPage[Report3Item]
Report4Page = ReportPage[Report4Item]
Report5Page = ReportPage[Report5Item]
Report6Page = ReportPage[Report6Item]
