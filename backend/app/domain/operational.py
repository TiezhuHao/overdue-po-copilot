"""Dataset-scoped operational queries. No ORM, generator or evaluation imports."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class StockpileAsOfSelector:
    def __init__(self, versions):
        self.versions = tuple(versions)

    def select(self, dataset_id, as_of):
        eligible = [v for v in self.versions if v.dataset_version_id == dataset_id
                    and v.is_valid and v.version_date <= as_of]
        return max(eligible, key=lambda v: (v.version_date, v.sequence_no), default=None)

    def lookup(self, records, dataset_id, material_id, as_of):
        version = self.select(dataset_id, as_of)
        if version is None:
            return StockpileLookup(None, None, 'NO_VALID_VERSION')
        record = next((r for r in records if r.dataset_version_id == dataset_id
                       and r.stockpile_version_id == version.stockpile_version_id
                       and r.material_id == material_id), None)
        return StockpileLookup(version, record, 'FOUND' if record is not None else 'MATERIAL_NOT_FOUND')


@dataclass(frozen=True)
class StockpileLookup:
    version: object
    record: object
    status: str


def future_months(version_date, count=6):
    first = version_date.year * 12 + version_date.month - 1
    return [date((first + i) // 12, (first + i) % 12 + 1, 1) for i in range(1, count + 1)]


def stockpile_achievement_ratio(actual, target):
    if actual < 0 or target < 0:
        raise ValueError('NEGATIVE_STOCKPILE_QUANTITY')
    return None if target == 0 else actual / target


def material_mpm_as_of(assignments, dataset_id, material_id, as_of):
    rows = [r for r in assignments if r.dataset_version_id == dataset_id and r.material_id == material_id
            and r.effective_from <= as_of and (r.effective_to is None or as_of < r.effective_to)]
    if len(rows) != 1:
        raise ValueError('MATERIAL_MPM_NOT_UNIQUE_AS_OF')
    return rows[0]


def cumulative_age_buckets(lots, thresholds):
    """Input lots expose age_days and quantity; thresholds are strictly exceeded."""
    return {t: sum((lot.quantity for lot in lots if lot.age_days > t), Decimal(0)) for t in thresholds}
