"""Grouped metric availability, without wrapping every primitive value."""

from enum import StrEnum
from uuid import UUID

from app.system_b.models import CalendarDate, CanonicalModel, Quantity


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class ReasonCode(StrEnum):
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FORECAST = "MISSING_FORECAST"
    INCOMPLETE_FORECAST_WINDOW = "INCOMPLETE_FORECAST_WINDOW"
    INVALID_FORECAST_WINDOW = "INVALID_FORECAST_WINDOW"
    NO_FORECAST_DEMAND = "NO_FORECAST_DEMAND"
    MISSING_STABLE_ID = "MISSING_STABLE_ID"
    INCOMPATIBLE_SCOPE = "INCOMPATIBLE_SCOPE"
    INCOMPARABLE_FORECAST_VERSIONS = "INCOMPARABLE_FORECAST_VERSIONS"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    UNCONFIRMED_SUPPLY_COMPOSITION = "UNCONFIRMED_SUPPLY_COMPOSITION"


class MetricResult(CanonicalModel):
    status: Availability
    reason_codes: tuple[ReasonCode, ...] = ()


class PoAgingMetrics(MetricResult):
    as_of_date: CalendarDate | None = None
    threshold_date: CalendarDate | None = None
    po_age_days: int | None = None
    threshold_days: int | None = None
    threshold_delta_days: int | None = None
    days_to_threshold: int | None = None
    days_beyond_threshold: int | None = None


class ForecastWindowMetrics(MetricResult):
    expected_week_count: int = 13
    observed_week_count: int = 0
    window_start_date: CalendarDate | None = None
    window_end_date_exclusive: CalendarDate | None = None
    observed_forecast_qty: Quantity | None = None
    total_forecast_qty: Quantity | None = None
    average_weekly_demand_qty: Quantity | None = None


class ConsumptionMetrics(MetricResult):
    forecast: ForecastWindowMetrics
    open_qty: Quantity | None = None
    estimated_consumption_weeks: Quantity | None = None


class SupplyDemandMetrics(MetricResult):
    all_supply_qty: Quantity | None = None
    actual_demand_total_qty: Quantity | None = None
    supply_demand_surplus_qty: Quantity | None = None
    purchase_requisition_qty: Quantity | None = None
    confirmed_supply_qty: Quantity | None = None
    planned_supply_qty: Quantity | None = None
    confirmed_gap_qty: Quantity | None = None
    planned_gap_qty: Quantity | None = None


class CoverageMetrics(MetricResult):
    forecast: ForecastWindowMetrics
    inventory_qty: Quantity | None = None
    inventory_coverage_weeks: Quantity | None = None
    confirmed_supply_coverage_weeks: Quantity | None = None
    planned_supply_coverage_weeks: Quantity | None = None


class ForecastChangeMetrics(MetricResult):
    forecast_month: CalendarDate | None = None
    previous_version_date: CalendarDate | None = None
    current_version_date: CalendarDate | None = None
    previous_forecast_qty: Quantity | None = None
    current_forecast_qty: Quantity | None = None
    forecast_change_qty: Quantity | None = None
    forecast_change_rate: Quantity | None = None


class AnalysisContext(CanonicalModel):
    dataset_version_id: UUID
    snapshot_date: CalendarDate
    material_code: str
    material_id: UUID | None


class PurchaseOrderAnalytics(AnalysisContext):
    po_number: str
    po_line_number: int
    shipment_number: int
    aging: PoAgingMetrics
    consumption: ConsumptionMetrics


class MaterialForecastAnalytics(AnalysisContext):
    consumption: ConsumptionMetrics
    coverage: CoverageMetrics
