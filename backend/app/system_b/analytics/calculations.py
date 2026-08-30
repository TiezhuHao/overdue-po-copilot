"""Pure metrics. Input association is explicit; no network, clock or rule engine."""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from app.system_b.models import (
    ForecastSnapshot, MaterialSupplyDemand, PurchaseOrder, WeekForecast, WeeklyForecastSnapshot,
)
from app.system_b.analytics.models import (
    Availability as A, ReasonCode as R, ConsumptionMetrics, CoverageMetrics,
    ForecastChangeMetrics, ForecastWindowMetrics, PoAgingMetrics, SupplyDemandMetrics,
)


# Explicit arithmetic context, independent of the caller's Decimal precision/traps.
DECIMAL_CONTEXT = Context(prec=40, rounding=ROUND_HALF_EVEN)
WEEK_COUNT = 13


def _valid_quantity(value: Decimal | None) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


def calculate_po_aging(
    order_date: date | None, material_lt_days: int | None, *, as_of_date: date | None,
) -> PoAgingMetrics:
    """Signed threshold delta and nonnegative distances; as_of_date is explicit."""
    if order_date is None or material_lt_days is None or as_of_date is None:
        return PoAgingMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.MISSING_REQUIRED_FIELD,))
    if (type(order_date) is not date or type(as_of_date) is not date
            or type(material_lt_days) is not int or material_lt_days < 0 or as_of_date < order_date):
        return PoAgingMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_INPUT,))
    threshold = material_lt_days + 180 + 60
    try:
        threshold_date = order_date + timedelta(days=threshold)
    except OverflowError:
        return PoAgingMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_INPUT,))
    age = (as_of_date - order_date).days
    return PoAgingMetrics(status=A.AVAILABLE, as_of_date=as_of_date, threshold_date=threshold_date,
                         po_age_days=age, threshold_days=threshold,
                         threshold_delta_days=age - threshold,
                         days_to_threshold=max(threshold - age, 0),
                         days_beyond_threshold=max(age - threshold, 0))


def calculate_forecast_window(weeks: Sequence[WeekForecast] | None) -> ForecastWindowMetrics:
    """Aggregate one material's canonical week buckets, never extrapolate missing weeks."""
    if weeks is None:
        return ForecastWindowMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.MISSING_FORECAST,))
    indices = [week.week_index for week in weeks]
    if (any(type(index) is not int or not 1 <= index <= WEEK_COUNT for index in indices)
            or len(set(indices)) != len(indices)):
        return ForecastWindowMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_FORECAST_WINDOW,),
                                     observed_week_count=len(weeks))
    if any(not _valid_quantity(week.forecast_qty) for week in weeks):
        return ForecastWindowMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_INPUT,),
                                     observed_week_count=len(weeks))
    with localcontext(DECIMAL_CONTEXT):
        observed = sum((week.forecast_qty for week in weeks), Decimal(0)) if weeks else None
        if set(indices) != set(range(1, WEEK_COUNT + 1)):
            return ForecastWindowMetrics(
                status=A.PARTIAL if weeks else A.NOT_COMPUTABLE,
                reason_codes=(R.INCOMPLETE_FORECAST_WINDOW,), observed_week_count=len(weeks),
                observed_forecast_qty=observed,
            )
        ordered = sorted(weeks, key=lambda week: week.week_index)
        dates = [week.week_start_date for week in ordered]
        start = end = None
        if any(day is not None for day in dates):
            if any(day is None for day in dates):
                return ForecastWindowMetrics(
                    status=A.PARTIAL, reason_codes=(R.INCOMPLETE_FORECAST_WINDOW,),
                    observed_week_count=WEEK_COUNT, observed_forecast_qty=observed,
                )
            if (any(type(day) is not date or day.weekday() != 0 for day in dates)
                    or any((dates[i] - dates[i - 1]).days != 7 for i in range(1, WEEK_COUNT))):
                return ForecastWindowMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_FORECAST_WINDOW,),
                                             observed_week_count=len(weeks))
            start = dates[0]
            try:
                end = dates[-1] + timedelta(days=7)
            except OverflowError:
                return ForecastWindowMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_FORECAST_WINDOW,),
                                             observed_week_count=len(weeks))
        return ForecastWindowMetrics(
            status=A.AVAILABLE, observed_week_count=WEEK_COUNT, observed_forecast_qty=observed,
            total_forecast_qty=observed, average_weekly_demand_qty=observed / Decimal(WEEK_COUNT),
            window_start_date=start, window_end_date_exclusive=end,
        )


def _quantity_in_weeks(quantity: Decimal | None, window: ForecastWindowMetrics):
    """Return ratio/status/reasons; input quantity must share the supplied bucket units."""
    if quantity is None:
        reason = R.MISSING_REQUIRED_FIELD
    elif not _valid_quantity(quantity):
        reason = R.INVALID_INPUT
    else:
        reason = None
    if window.status != A.AVAILABLE:
        return None, window.status, tuple(dict.fromkeys((*window.reason_codes, *((reason,) if reason else ()))))
    if reason:
        return None, A.PARTIAL, (reason,)
    if window.total_forecast_qty == 0:
        return None, A.PARTIAL, (R.NO_FORECAST_DEMAND,)
    with localcontext(DECIMAL_CONTEXT):
        # One division avoids rounding an intermediate repeating weekly average.
        return quantity * Decimal(WEEK_COUNT) / window.total_forecast_qty, A.AVAILABLE, ()


def calculate_consumption(
    open_qty: Decimal | None, weeks: Sequence[WeekForecast] | None,
) -> ConsumptionMetrics:
    """Scalar primitive: caller supplies quantities from the same material/UOM scope."""
    window = calculate_forecast_window(weeks)
    value, status, reasons = _quantity_in_weeks(open_qty, window)
    return ConsumptionMetrics(status=status, reason_codes=reasons, forecast=window,
                              open_qty=open_qty if _valid_quantity(open_qty) else None,
                              estimated_consumption_weeks=value)


def calculate_coverage(
    available_inventory_qty: Decimal | None, weeks: Sequence[WeekForecast] | None,
) -> CoverageMetrics:
    """Available inventory coverage; confirmed/planned composition is not established."""
    window = calculate_forecast_window(weeks)
    value, _, reasons = _quantity_in_weeks(available_inventory_qty, window)
    return CoverageMetrics(
        status=A.PARTIAL if value is not None or window.observed_forecast_qty is not None else A.NOT_COMPUTABLE,
        reason_codes=(*reasons, R.UNCONFIRMED_SUPPLY_COMPOSITION), forecast=window,
        inventory_qty=available_inventory_qty if _valid_quantity(available_inventory_qty) else None,
        inventory_coverage_weeks=value,
    )


def calculate_supply_demand(source: MaterialSupplyDemand | None) -> SupplyDemandMetrics:
    """Recompute the established source surplus; do not reclassify supply or add PR."""
    if source is None:
        return SupplyDemandMetrics(status=A.NOT_COMPUTABLE,
                                   reason_codes=(R.MISSING_REQUIRED_FIELD, R.UNCONFIRMED_SUPPLY_COMPOSITION))
    supply, demand, pr = source.all_supply_qty, source.actual_demand_total_qty, source.purchase_requisition_qty
    if not _valid_quantity(supply) or not _valid_quantity(demand):
        return SupplyDemandMetrics(status=A.NOT_COMPUTABLE,
                                   reason_codes=(R.INVALID_INPUT, R.UNCONFIRMED_SUPPLY_COMPOSITION))
    reasons = [R.UNCONFIRMED_SUPPLY_COMPOSITION]
    if pr is not None and not _valid_quantity(pr):
        reasons.append(R.INVALID_INPUT)
        pr = None
    with localcontext(DECIMAL_CONTEXT):
        return SupplyDemandMetrics(
            status=A.PARTIAL, reason_codes=tuple(reasons), all_supply_qty=supply,
            actual_demand_total_qty=demand, supply_demand_surplus_qty=supply - demand,
            purchase_requisition_qty=pr,
        )


def _po_forecast_scope(po: PurchaseOrder, forecast: WeeklyForecastSnapshot) -> R | None:
    if po.dataset_version_id != forecast.dataset_version_id or po.snapshot_date != forecast.snapshot_date:
        return R.INCOMPATIBLE_SCOPE
    if any(value is None for value in (po.material_id, forecast.material_id, po.organization_id, forecast.organization_id)):
        return R.MISSING_STABLE_ID
    if po.material_id != forecast.material_id or po.organization_id != forecast.organization_id:
        return R.INCOMPATIBLE_SCOPE
    return None


def calculate_po_consumption(
    po: PurchaseOrder | None, forecast: WeeklyForecastSnapshot | None,
) -> ConsumptionMetrics:
    if po is None or forecast is None:
        reason = R.MISSING_REQUIRED_FIELD if po is None else R.MISSING_FORECAST
    else:
        reason = _po_forecast_scope(po, forecast)
    if reason:
        # Do not attach another/unverified material's forecast to this PO result.
        window = ForecastWindowMetrics(status=A.NOT_COMPUTABLE, reason_codes=(reason,))
        return ConsumptionMetrics(status=A.NOT_COMPUTABLE, reason_codes=(reason,), forecast=window)
    return calculate_consumption(po.overdue_open_qty, forecast.weeks)


def calculate_forecast_change(
    previous: ForecastSnapshot | None, current: ForecastSnapshot | None,
) -> ForecastChangeMetrics:
    """Compare an explicit pair of same-month facts; never discover previous/current."""
    if previous is None or current is None:
        return ForecastChangeMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.MISSING_FORECAST,))
    if any(value is None for value in (
        previous.material_id, current.material_id, previous.project_id, current.project_id,
        previous.forecast_version_id, current.forecast_version_id,
    )):
        return ForecastChangeMetrics(status=A.NOT_COMPUTABLE,
                                     reason_codes=(R.INCOMPARABLE_FORECAST_VERSIONS, R.MISSING_STABLE_ID))
    if (previous.dataset_version_id != current.dataset_version_id
            or previous.snapshot_date != current.snapshot_date
            or previous.material_id != current.material_id or previous.project_id != current.project_id
            or previous.po_line_schedule_id != current.po_line_schedule_id
            or previous.forecast_month != current.forecast_month):
        return ForecastChangeMetrics(status=A.NOT_COMPUTABLE,
                                     reason_codes=(R.INCOMPARABLE_FORECAST_VERSIONS, R.INCOMPATIBLE_SCOPE))
    if (previous.forecast_month.day != 1
            or not previous.forecast_version_date < current.forecast_version_date <= current.snapshot_date
            or previous.forecast_version_id == current.forecast_version_id):
        return ForecastChangeMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INCOMPARABLE_FORECAST_VERSIONS,))
    old, new = previous.forecast_qty, current.forecast_qty
    if not _valid_quantity(old) or not _valid_quantity(new):
        return ForecastChangeMetrics(status=A.NOT_COMPUTABLE, reason_codes=(R.INVALID_INPUT,))
    with localcontext(DECIMAL_CONTEXT):
        change = new - old
        return ForecastChangeMetrics(
            status=A.PARTIAL if old == 0 else A.AVAILABLE,
            reason_codes=(R.ZERO_DENOMINATOR,) if old == 0 else (), forecast_month=previous.forecast_month,
            previous_version_date=previous.forecast_version_date, current_version_date=current.forecast_version_date,
            previous_forecast_qty=old, current_forecast_qty=new, forecast_change_qty=change,
            forecast_change_rate=None if old == 0 else change / old,
        )
