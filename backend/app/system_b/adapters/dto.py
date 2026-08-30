"""Consumer-owned subset of actual System A JSON, independent of A imports."""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.system_b.models import CalendarDate, LifecycleStage, NonnegativeInt, PositiveInt, Quantity


class SourceDTO(BaseModel):
    # Unconsumed presentation fields are accepted but never retained or forwarded.
    model_config = ConfigDict(extra="ignore")


class DatasetDTO(SourceDTO):
    dataset_version_id: UUID
    dataset_version_name: str
    snapshot_date: CalendarDate
    status: Literal["GENERATING", "READY", "FAILED", "RETIRED"]
    generation_signature: str
    business_content_hash: str | None


class DatasetListDTO(SourceDTO):
    items: list[DatasetDTO]
    total: NonnegativeInt


class PurchaseOrderDTO(SourceDTO):
    material_id: UUID | None = None
    po_header_id: UUID | None = None
    po_line_id: UUID | None = None
    po_line_schedule_id: UUID | None = None
    po_reference_project_id: UUID | None = None
    supplier_id: UUID | None = None
    organization_id: UUID | None = None
    material_code: str
    po_number: str
    po_line_number: PositiveInt
    shipment_number: PositiveInt
    inventory_organization_code: str
    inventory_organization_type: str
    supplier_code: str
    supplier_name: str
    reference_project_code: str | None
    reference_project_name: str | None
    order_date: CalendarDate
    due_date: CalendarDate
    snapshot_date: CalendarDate
    material_lt_days: NonnegativeInt
    schedule_qty: Quantity
    schedule_received_qty: Quantity
    overdue_open_qty: Quantity
    overdue_days: Annotated[int, Field(strict=True)]
    is_overdue: StrictBool
    po_status: str
    close_status: str
    can_close: StrictBool
    completion_at: AwareDatetime | None


class SupplyDemandDTO(SourceDTO):
    material_id: UUID | None = None
    organization_id: UUID | None = None
    supply_demand_snapshot_id: UUID | None = None
    inventory_snapshot_id: UUID | None = None
    mpm_employee_id: UUID | None = None
    supply_snapshot_date: CalendarDate | None = None
    inventory_snapshot_date: CalendarDate | None = None
    material_code: str
    inventory_organization_code: str
    material_lt_days: NonnegativeInt
    all_supply_qty: Quantity
    actual_demand_total_qty: Quantity
    supply_demand_surplus_qty: Quantity
    good_non_vmi_inventory_qty: Quantity | None
    defective_inventory_qty: Quantity | None
    non_mrp_inventory_qty: Quantity | None
    non_vmi_in_transit_order_qty: Quantity | None
    non_vmi_in_transit_delivery_qty: Quantity | None
    open_po_qty: Quantity | None
    purchase_requisition_qty: Quantity | None
    organization_active_projects: list[str] | None
    enterprise_active_projects: list[str] | None
    top_project: str | None
    mpm_code: str
    mpm_name: str
    mpm_department_name: str


class ForecastDTO(SourceDTO):
    material_id: UUID | None = None
    project_id: UUID | None = None
    forecast_version_id: UUID | None = None
    forecast_version_sequence: PositiveInt | None = None
    forecast_anchor_date: CalendarDate | None = None
    window_position: NonnegativeInt | None = None
    horizon_start_month: CalendarDate | None = None
    horizon_end_month_exclusive: CalendarDate | None = None
    material_code: str
    po_line_schedule_id: UUID
    project_name: str
    forecast_version_name: str
    forecast_version_date: CalendarDate
    window_role: Literal["BASELINE", "POST"]
    forecast_month: CalendarDate
    forecast_qty: Quantity
    forecast_total_qty: Quantity
    cumulative_shipped_qty: Quantity


class WeekEvidenceDTO(SourceDTO):
    week_index: Annotated[int, Field(strict=True, ge=1, le=13)]
    week_start_date: CalendarDate
    forecast_qty: Quantity


class ProjectWeekDTO(WeekEvidenceDTO):
    project_id: UUID


class WeeklyForecastDTO(SourceDTO):
    material_id: UUID | None = None
    organization_id: UUID | None = None
    weekly_forecast_snapshot_id: UUID | None = None
    source_forecast_version_id: UUID | None = None
    forecast_snapshot_date: CalendarDate | None = None
    weeks: list[WeekEvidenceDTO] | None = None
    project_contributions: list[ProjectWeekDTO] | None = None
    material_code: str
    organization_code: str
    snapshot_date: CalendarDate
    week_01_forecast_qty: Quantity
    week_02_forecast_qty: Quantity
    week_03_forecast_qty: Quantity
    week_04_forecast_qty: Quantity
    week_05_forecast_qty: Quantity
    week_06_forecast_qty: Quantity
    week_07_forecast_qty: Quantity
    week_08_forecast_qty: Quantity
    week_09_forecast_qty: Quantity
    week_10_forecast_qty: Quantity
    week_11_forecast_qty: Quantity
    week_12_forecast_qty: Quantity
    week_13_forecast_qty: Quantity
    thirteen_week_demand_qty: Quantity
    weekly_average_demand_qty: Quantity
    open_po_qty: Quantity | None
    advance_shipping_notice_qty: Quantity | None
    open_purchase_requisition_qty: Quantity | None
    good_subinventory_qty: Quantity | None
    defective_subinventory_qty: Quantity | None
    top_project: str | None

    @model_validator(mode="after")
    def validate_week_evidence(self):
        if self.weeks is not None:
            ordered = sorted(self.weeks, key=lambda week: week.week_index)
            if [week.week_index for week in ordered] != list(range(1, 14)):
                raise ValueError("incomplete or duplicate week evidence")
            for week in ordered:
                if (week.week_start_date.weekday() != 0
                        or (week.week_start_date - ordered[0].week_start_date).days != 7 * (week.week_index - 1)
                        or week.forecast_qty != getattr(self, f"week_{week.week_index:02d}_forecast_qty")):
                    raise ValueError("inconsistent week evidence")
        if self.project_contributions is not None:
            if self.weeks is None:
                raise ValueError("project evidence requires week evidence")
            seen = set()
            dates = {week.week_index: week.week_start_date for week in self.weeks}
            for item in self.project_contributions:
                key = (item.project_id, item.week_index)
                if key in seen or item.week_start_date != dates[item.week_index] or item.forecast_qty < 0:
                    raise ValueError("invalid project week evidence")
                seen.add(key)
        return self


class ProductConfigDTO(SourceDTO):
    material_id: UUID | None = None
    project_id: UUID | None = None
    product_config_id: UUID | None = None
    material_code: str
    project_name: str
    product_config_type: str
    product_config_name: str
    product_config_version: str
    product_config_status: str
    business_unit_name: str
    planning_department_name: str
    lifecycle_stage: LifecycleStage
    customer_code: str | None
    customer_project_name: str | None
    modified_at: AwareDatetime | None


class TemporalQuantityDTO(SourceDTO):
    period: CalendarDate
    quantity: Quantity


class AgeQuantityDTO(SourceDTO):
    threshold_days: PositiveInt
    quantity: Quantity


class StockpileDTO(SourceDTO):
    material_id: UUID | None = None
    organization_id: UUID | None = None
    stockpile_version_id: UUID | None = None
    stockpile_record_id: UUID | None = None
    actual_stockpile_qty: Quantity | None = None
    stockpile_version_sequence: PositiveInt | None = None
    material_code: str
    stockpile_version_name: str
    stockpile_version_date: CalendarDate
    stockpile_nature: str
    planned_stockpile_qty: Quantity
    inventory_qty: Quantity
    seven_day_demand_qty: Quantity
    stockpile_qty_gap: Quantity
    stockpile_completion_ratio: Quantity | None
    agreement_unit_price: Quantity | None
    future_months: list[TemporalQuantityDTO]
    inventory_age_quantities: list[AgeQuantityDTO]


S = TypeVar("S", bound=SourceDTO)


class StockpileSelectionDTO(SourceDTO):
    as_of_date: CalendarDate
    stockpile_version_id: UUID | None = None
    stockpile_version_date: CalendarDate | None = None
    sequence_no: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_selection(self):
        values = (self.stockpile_version_id, self.stockpile_version_date, self.sequence_no)
        if any(value is None for value in values) and not all(value is None for value in values):
            raise ValueError("incomplete version selection")
        if self.stockpile_version_date is not None and self.stockpile_version_date > self.as_of_date:
            raise ValueError("future version selection")
        return self


class ReportPageDTO(SourceDTO, Generic[S]):
    dataset_version_id: UUID
    snapshot_date: CalendarDate
    page: PositiveInt
    page_size: Annotated[int, Field(strict=True, ge=1, le=500)]
    total: NonnegativeInt
    items: list[S]
    stockpile_selection: StockpileSelectionDTO | None = None
