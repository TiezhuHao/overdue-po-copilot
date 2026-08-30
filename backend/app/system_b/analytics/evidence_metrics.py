"""Neutral project aggregation and aligned month comparisons; no business labels."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
from uuid import UUID

from app.system_b.analytics.calculations import DECIMAL_CONTEXT, calculate_forecast_window
from app.system_b.analytics.models import Availability as A
from app.system_b.models import CalendarDate, CanonicalModel, ForecastSnapshot, PurchaseOrder, Quantity, WeeklyForecastSnapshot


class ProjectContributionMetrics(CanonicalModel):
    project_id: UUID
    total_contribution_qty: Quantity
    contribution_share: Quantity | None
    average_weekly_qty: Quantity
    nonzero_week_count: int
    longest_nonzero_run: int


class ProjectExposureMetrics(CanonicalModel):
    status: A
    reason_codes: tuple[str, ...] = ()
    rankings: tuple[ProjectContributionMetrics, ...] = ()
    top_contributing_project: UUID | None = None


class PeriodChange(CanonicalModel):
    period: CalendarDate
    previous_qty: Quantity
    current_qty: Quantity
    change_qty: Quantity


class AlignedComparison(CanonicalModel):
    project_id: UUID
    previous_version_id: UUID
    current_version_id: UUID
    previous_version_date: CalendarDate
    current_version_date: CalendarDate
    post_position: int
    periods: tuple[PeriodChange, ...]
    aligned_previous_total: Quantity
    aligned_current_total: Quantity
    total_change_qty: Quantity
    total_change_rate: Quantity | None
    later_shift_qty: Quantity
    later_shift_share: Quantity | None


class AnchorComparisonMetrics(CanonicalModel):
    status: A
    reason_codes: tuple[str, ...] = ()
    comparisons: tuple[AlignedComparison, ...] = ()


def calculate_project_exposure(weekly: WeeklyForecastSnapshot | None) -> ProjectExposureMetrics:
    def unavailable(code):
        return ProjectExposureMetrics(status=A.NOT_COMPUTABLE, reason_codes=(code,))

    if weekly is None or weekly.project_contributions is None:
        return unavailable("MISSING_PROJECT_CONTRIBUTIONS")
    if any(value is None for value in (weekly.material_id, weekly.organization_id, weekly.weekly_forecast_snapshot_id,
                                       weekly.source_forecast_version_id, weekly.forecast_snapshot_date)):
        return unavailable("MISSING_STABLE_ID")
    window = calculate_forecast_window(weekly.weeks)
    if window.status != A.AVAILABLE or window.window_start_date is None:
        return unavailable("INCOMPLETE_FORECAST_WINDOW")
    if weekly.forecast_snapshot_date > weekly.snapshot_date:
        return unavailable("FUTURE_OBSERVATION")
    first = weekly.forecast_snapshot_date + timedelta(days=(-weekly.forecast_snapshot_date.weekday()) % 7)
    if window.window_start_date != first:
        return unavailable("WEEKLY_WINDOW_MISMATCH")
    groups = defaultdict(dict)
    dates = {week.week_index: week.week_start_date for week in weekly.weeks}
    for row in weekly.project_contributions:
        if (row.week_index in groups[row.project_id] or row.forecast_qty < 0
                or row.week_start_date != dates.get(row.week_index)):
            return unavailable("INVALID_PROJECT_WEEK_EVIDENCE")
        groups[row.project_id][row.week_index] = row.forecast_qty
    # Missing project-week cells are unknown, never inferred zeros.
    if any(set(rows) != set(range(1, 14)) for rows in groups.values()):
        return unavailable("INCOMPLETE_PROJECT_WINDOW")
    with localcontext(DECIMAL_CONTEXT):
        for week in weekly.weeks:
            if sum((groups[pid][week.week_index] for pid in sorted(groups, key=str)), Decimal(0)) != week.forecast_qty:
                return unavailable("PROJECT_CONTRIBUTION_TOTAL_MISMATCH")
        total = window.total_forecast_qty
        ranking = []
        for project_id, rows in groups.items():
            quantity = sum((rows[index] for index in range(1, 14)), Decimal(0))
            run = longest = 0
            for index in range(1, 14):
                run = run + 1 if rows[index] > 0 else 0
                longest = max(longest, run)
            ranking.append(ProjectContributionMetrics(project_id=project_id, total_contribution_qty=quantity,
                contribution_share=quantity / total if total else None, average_weekly_qty=quantity / Decimal(13),
                nonzero_week_count=sum(value > 0 for value in rows.values()), longest_nonzero_run=longest))
        # UUID orders presentation within a tie only; it never chooses a winner.
        ranking.sort(key=lambda row: (-row.total_contribution_qty, str(row.project_id)))
        if not ranking or total == 0:
            return ProjectExposureMetrics(status=A.NOT_COMPUTABLE, reason_codes=("NO_POSITIVE_PROJECT_DEMAND",), rankings=tuple(ranking))
        if len(ranking) > 1 and ranking[0].total_contribution_qty == ranking[1].total_contribution_qty:
            return ProjectExposureMetrics(status=A.PARTIAL, reason_codes=("AMBIGUOUS_TOP_PROJECT",), rankings=tuple(ranking))
        return ProjectExposureMetrics(status=A.AVAILABLE, rankings=tuple(ranking), top_contributing_project=ranking[0].project_id)


def _month_range(start: date, end: date) -> tuple[date, ...]:
    if start.day != 1 or end.day != 1 or end <= start:
        return ()
    count = (end.year - start.year) * 12 + end.month - start.month
    # R3 explicitly exposes seven months, not an arbitrary unbounded range.
    if count != 7:
        return ()
    return tuple(date((start.year * 12 + start.month - 1 + i) // 12,
                      (start.year * 12 + start.month - 1 + i) % 12 + 1, 1) for i in range(count))


def calculate_anchor_comparisons(po: PurchaseOrder, project_id: UUID | None,
                                 history: tuple[ForecastSnapshot, ...] | None) -> AnchorComparisonMetrics:
    def unavailable(code):
        return AnchorComparisonMetrics(status=A.NOT_COMPUTABLE, reason_codes=(code,))

    if project_id is None:
        return unavailable("MISSING_SELECTED_PROJECT")
    rows = [row for row in history or () if row.project_id == project_id]
    if not rows:
        return unavailable("MISSING_FORECAST_HISTORY")
    try:
        anchor = po.order_date + timedelta(days=po.material_lt_days)
    except OverflowError:
        return unavailable("INVALID_ANCHOR_DATE")
    groups = defaultdict(list)
    for row in rows:
        if (po.material_id is None or po.po_line_schedule_id is None
                or (row.dataset_version_id, row.snapshot_date, row.material_id, row.po_line_schedule_id)
                != (po.dataset_version_id, po.snapshot_date, po.material_id, po.po_line_schedule_id)):
            return unavailable("INCOMPATIBLE_SCOPE")
        if any(value is None for value in (row.forecast_version_id, row.forecast_version_sequence,
                   row.window_position, row.horizon_start_month, row.horizon_end_month_exclusive)):
            return unavailable("MISSING_VERSION_METADATA")
        if row.forecast_anchor_date != anchor or row.forecast_version_date > po.snapshot_date:
            return unavailable("ANCHOR_TIME_MISMATCH")
        if row.forecast_qty < 0:
            return unavailable("INVALID_INPUT")
        groups[row.window_position].append(row)
    positions = sorted(groups)
    if positions != list(range(len(positions))) or not 3 <= len(positions) <= 6:
        return unavailable("INCOMPLETE_ANCHOR_WINDOW")
    versions = []
    for position in positions:
        records = groups[position]
        head = records[0]
        metadata = lambda row: (row.forecast_version_id, row.forecast_version_date, row.forecast_version_sequence,
                                row.window_role, row.horizon_start_month, row.horizon_end_month_exclusive)
        if any(metadata(row) != metadata(head) for row in records):
            return unavailable("INCONSISTENT_VERSION_METADATA")
        if (head.window_role != ("BASELINE" if position == 0 else "POST")
                or not (head.forecast_version_date < anchor if position == 0 else head.forecast_version_date > anchor)):
            return unavailable("ANCHOR_TIME_MISMATCH")
        periods = _month_range(head.horizon_start_month, head.horizon_end_month_exclusive)
        if (head.horizon_start_month != head.forecast_version_date.replace(day=1)
                or not periods or len(records) != len(periods) or {row.forecast_month for row in records} != set(periods)):
            return unavailable("INCOMPLETE_COMPARABLE_WINDOW")
        versions.append((head, {row.forecast_month: row.forecast_qty for row in records}))
    heads = [head for head, _ in versions]
    if (len({head.forecast_version_id for head in heads}) != len(heads)
            or any(heads[i].forecast_version_date >= heads[i + 1].forecast_version_date for i in range(len(heads) - 1))):
        return unavailable("INCOMPARABLE_FORECAST_VERSIONS")
    common = sorted(set.intersection(*(set(values) for _, values in versions)))
    if len(common) < 2:
        return unavailable("INCOMPLETE_COMPARABLE_WINDOW")
    before, previous = versions[0]
    comparisons = []
    with localcontext(DECIMAL_CONTEXT):
        for after, current in versions[1:]:
            cells = tuple(PeriodChange(period=month, previous_qty=previous[month], current_qty=current[month],
                                       change_qty=current[month] - previous[month]) for month in common)
            old = sum((cell.previous_qty for cell in cells), Decimal(0))
            new = sum((cell.current_qty for cell in cells), Decimal(0))
            earlier_deficit = shift = Decimal(0)
            for cell in cells:
                if cell.change_qty < 0:
                    earlier_deficit -= cell.change_qty
                elif cell.change_qty > 0:
                    moved = min(earlier_deficit, cell.change_qty)
                    shift += moved
                    earlier_deficit -= moved
            comparisons.append(AlignedComparison(project_id=project_id, previous_version_id=before.forecast_version_id,
                current_version_id=after.forecast_version_id, previous_version_date=before.forecast_version_date,
                current_version_date=after.forecast_version_date, post_position=after.window_position, periods=cells,
                aligned_previous_total=old, aligned_current_total=new, total_change_qty=new - old,
                total_change_rate=(new - old) / old if old else None,
                later_shift_qty=shift, later_shift_share=shift / old if old else None))
    return AnchorComparisonMetrics(status=A.AVAILABLE, comparisons=tuple(comparisons))
