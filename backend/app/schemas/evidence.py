"""Additive REST evidence fields, independent of the Excel presentation manifest."""
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WeekEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_index: Annotated[int, Field(ge=1, le=13)]
    week_start_date: date
    forecast_qty: Decimal


class ProjectWeekEvidence(WeekEvidence):
    project_id: UUID


class StockpileSelection(BaseModel):
    as_of_date: date
    stockpile_version_id: UUID | None = None
    stockpile_version_date: date | None = None
    sequence_no: int | None = None


IDENTITY_FIELDS = {
    1: ("material_id", "po_header_id", "po_line_id", "po_line_schedule_id", "po_reference_project_id", "supplier_id", "organization_id"),
    2: ("material_id", "organization_id", "supply_demand_snapshot_id", "inventory_snapshot_id", "mpm_employee_id"),
    3: ("material_id", "project_id", "forecast_version_id"),
    4: ("material_id", "organization_id", "weekly_forecast_snapshot_id", "source_forecast_version_id"),
    5: ("material_id", "project_id", "product_config_id"),
    6: ("material_id", "organization_id", "stockpile_version_id", "stockpile_record_id"),
}


def evidence_fields(report_id):
    fields = {name: (UUID | None, None) for name in IDENTITY_FIELDS[report_id]}
    additions = {
        2: {"supply_snapshot_date": (date | None, None), "inventory_snapshot_date": (date | None, None)},
        3: {"forecast_version_sequence": (int | None, None), "forecast_anchor_date": (date | None, None),
            "window_position": (int | None, None), "horizon_start_month": (date | None, None),
            "horizon_end_month_exclusive": (date | None, None)},
        4: {"forecast_snapshot_date": (date | None, None), "weeks": (list[WeekEvidence] | None, None),
            "project_contributions": (list[ProjectWeekEvidence] | None, None)},
        6: {"stockpile_version_sequence": (int | None, None), "actual_stockpile_qty": (Decimal | None, None)},
    }
    return fields | additions.get(report_id, {})
