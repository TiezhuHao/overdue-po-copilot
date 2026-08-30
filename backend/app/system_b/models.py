"""Typed evidence contracts; no procurement calculations or inferred identities."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StrictBool


def _decimal_input(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a quantity")
    return value


def _date_input(value):
    if type(value) is date:
        return value
    if isinstance(value, str) and len(value) == 10 and value[4] == value[7] == "-":
        return date.fromisoformat(value)
    raise ValueError("date must be YYYY-MM-DD or a date object")


Quantity = Annotated[Decimal, BeforeValidator(_decimal_input), Field(allow_inf_nan=False)]
CalendarDate = Annotated[date, BeforeValidator(_date_input)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
LifecycleStage = Literal["NPI", "MASS_PRODUCTION", "EOL"]


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetMetadata(CanonicalModel):
    dataset_version_id: UUID
    dataset_version_name: str
    snapshot_date: CalendarDate
    status: Literal["GENERATING", "READY", "FAILED", "RETIRED"]
    generation_signature: str
    business_content_hash: str | None


class Evidence(CanonicalModel):
    dataset_version_id: UUID
    snapshot_date: CalendarDate
    material_code: str
    # Nullable for legacy REST responses; enriched responses reuse source identity.
    material_id: UUID | None = None


class PurchaseOrder(Evidence):
    """One PO schedule/shipment, not a PO header or line aggregate."""

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
    po_header_id: UUID | None = None
    po_line_schedule_id: UUID | None = None
    po_line_id: UUID | None = None
    po_reference_project_id: UUID | None = None
    supplier_id: UUID | None = None
    organization_id: UUID | None = None
    unit_price: Quantity | None = None
    currency: str | None = None


class MaterialMpmContact(CanonicalModel):
    employee_code: str
    employee_name: str
    department_name: str
    employee_id: UUID | None = None


class MaterialSupplyDemand(Evidence):
    supply_demand_snapshot_id: UUID | None = None
    inventory_snapshot_id: UUID | None = None
    supply_snapshot_date: CalendarDate | None = None
    inventory_snapshot_date: CalendarDate | None = None
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
    organization_active_projects: tuple[str, ...] | None
    enterprise_active_projects: tuple[str, ...] | None
    top_project: str | None
    mpm: MaterialMpmContact
    organization_id: UUID | None = None


class ForecastSnapshot(Evidence):
    """One month in an upstream-selected schedule/project/version window."""

    po_line_schedule_id: UUID
    project_name: str
    forecast_version_name: str
    forecast_version_date: CalendarDate
    window_role: Literal["BASELINE", "POST"]
    forecast_month: CalendarDate
    forecast_qty: Quantity
    forecast_total_qty: Quantity
    cumulative_shipped_qty: Quantity
    project_id: UUID | None = None
    forecast_version_id: UUID | None = None
    forecast_version_sequence: PositiveInt | None = None
    forecast_anchor_date: CalendarDate | None = None
    window_position: NonnegativeInt | None = None
    horizon_start_month: CalendarDate | None = None
    horizon_end_month_exclusive: CalendarDate | None = None


class WeekForecast(CanonicalModel):
    week_index: Annotated[int, Field(strict=True, ge=1, le=13)]
    forecast_qty: Quantity
    week_start_date: CalendarDate | None = None


class ProjectWeekForecast(WeekForecast):
    project_id: UUID


class WeeklyForecastSnapshot(Evidence):
    organization_code: str
    weeks: Annotated[tuple[WeekForecast, ...], Field(min_length=13, max_length=13)]
    thirteen_week_demand_qty: Quantity
    weekly_average_demand_qty: Quantity
    open_po_qty: Quantity | None
    advance_shipping_notice_qty: Quantity | None
    open_purchase_requisition_qty: Quantity | None
    good_subinventory_qty: Quantity | None
    defective_subinventory_qty: Quantity | None
    top_project: str | None
    organization_id: UUID | None = None
    weekly_forecast_snapshot_id: UUID | None = None
    forecast_snapshot_date: CalendarDate | None = None
    source_forecast_version_id: UUID | None = None
    project_contributions: tuple[ProjectWeekForecast, ...] | None = None


class ProductConfig(Evidence):
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
    project_id: UUID | None = None
    product_config_id: UUID | None = None


class TemporalQuantity(CanonicalModel):
    period: CalendarDate
    quantity: Quantity


class AgeQuantity(CanonicalModel):
    threshold_days: PositiveInt
    quantity: Quantity


class StockpileRecord(Evidence):
    """Versioned material evidence; page selection records the requested as-of date."""

    stockpile_version_name: str
    stockpile_version_date: CalendarDate
    stockpile_tag: str
    target_stockpile_qty: Quantity
    inventory_qty: Quantity
    seven_day_demand_qty: Quantity
    stockpile_qty_gap: Quantity
    stockpile_completion_ratio: Quantity | None
    agreement_unit_price: Quantity | None
    future_months: tuple[TemporalQuantity, ...]
    inventory_age_quantities: tuple[AgeQuantity, ...]
    stockpile_version_id: UUID | None = None
    stockpile_record_id: UUID | None = None
    actual_stockpile_qty: Quantity | None = None
    organization_id: UUID | None = None
    stockpile_version_sequence: PositiveInt | None = None
    currency: str | None = None


class StockpileSelection(CanonicalModel):
    as_of_date: CalendarDate
    stockpile_version_id: UUID | None = None
    stockpile_version_date: CalendarDate | None = None
    sequence_no: PositiveInt | None = None


T = TypeVar("T", bound=CanonicalModel)


class CanonicalPage(CanonicalModel, Generic[T]):
    dataset_version_id: UUID
    snapshot_date: CalendarDate
    page: PositiveInt
    page_size: Annotated[int, Field(strict=True, ge=1, le=500)]
    total: NonnegativeInt
    items: tuple[T, ...]
    stockpile_selection: StockpileSelection | None = None
