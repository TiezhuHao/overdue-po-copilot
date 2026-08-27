"""Quantity and publication-window queries without evaluation dependencies."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


def forecast_anchor(order_date, material_lt_days):
    if material_lt_days < 0:
        raise ValueError('INVALID_MATERIAL_LEAD_TIME')
    return order_date + timedelta(days=material_lt_days)


def week_one_start(snapshot_date):
    return snapshot_date + timedelta(days=(-snapshot_date.weekday()) % 7)


def daily_final_versions(versions, dataset_version_id):
    final = {}
    for version in versions:
        if version.dataset_version_id != dataset_version_id or not version.is_valid:
            continue
        existing = final.get(version.version_date)
        if existing is not None and existing.sequence_no == version.sequence_no:
            raise ValueError('DUPLICATE_FORECAST_VERSION_SEQUENCE')
        if existing is None or version.sequence_no > existing.sequence_no:
            final[version.version_date] = version
    return [final[day] for day in sorted(final)]


@dataclass(frozen=True)
class ForecastWindow:
    baseline: object
    post_versions: tuple

    @property
    def ordered_window(self):
        return (self.baseline, *self.post_versions)


class ForecastWindowSelector:
    def __init__(self, versions):
        self.versions = tuple(versions)

    def select(self, dataset_version_id, forecast_anchor_date, after_versions=3):
        if type(after_versions) is not int or not 2 <= after_versions <= 5:
            raise ValueError('AFTER_VERSIONS_OUT_OF_RANGE')
        final = daily_final_versions(self.versions, dataset_version_id)
        before = [v for v in final if v.version_date < forecast_anchor_date]
        after = [v for v in final if v.version_date > forecast_anchor_date][:after_versions]
        if not before or len(after) != after_versions:
            raise ValueError('INCOMPLETE_FORECAST_WINDOW')
        return ForecastWindow(before[-1], tuple(after))


def thirteen_week_totals(rows):
    rows = list(rows)
    if len(rows) != 13 or {r.week_index for r in rows} != set(range(1, 14)):
        raise ValueError('INCOMPLETE_THIRTEEN_WEEK_FORECAST')
    if any(r.forecast_qty < 0 for r in rows):
        raise ValueError('NEGATIVE_FORECAST_QUANTITY')
    total = sum((r.forecast_qty for r in rows), Decimal(0))
    return {'thirteen_week_demand_qty': total, 'weekly_average_demand_qty': total / 13}


def top_project(rows):
    totals = {}
    for row in rows:
        totals[row.project_id] = totals.get(row.project_id, Decimal(0)) + row.forecast_qty
    return min(totals, key=lambda key: (-totals[key], str(key))) if totals else None


def cumulative_shipped_qty(rows, dataset_id, material_id, project_id, version_date):
    return sum((r.shipped_qty for r in rows if r.dataset_version_id == dataset_id
                and r.material_id == material_id and r.project_id == project_id
                and r.shipment_date <= version_date), Decimal(0))
