from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta


def add_months(value: date, months: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + months
    year, month = divmod(ordinal, 12)
    return date(year, month + 1, min(value.day, monthrange(year, month + 1)[1]))


def days(start: date, end: date):
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def active(row, as_of: date) -> bool:
    return row.effective_from <= as_of and (row.effective_to is None or as_of < row.effective_to)


def material_anchors(scenario, procurement):
    lines = {row.po_line_id: row for row in procurement.po_lines}
    result = defaultdict(set)
    for row in scenario.scenario_truth_rows:
        line = lines[row.po_line_id]
        result[line.material_id].add(line.order_date + timedelta(days=line.material_lt_days_at_order))
    return {key: sorted(value) for key, value in result.items()}


def source_cycles(anchors):
    """Each event is effective on its anchor, independent of publication weekday."""
    return [(anchor - timedelta(days=1), anchor, anchor.replace(day=1))
            for anchor in sorted(set(anchors))]


def demand_horizon(snapshot, scenario, procurement, config):
    anchors = [anchor for values in material_anchors(scenario, procurement).values() for anchor in values]
    earliest = min(anchors) if anchors else snapshot
    # Include the historical stockpile version preceding the earliest order as well.
    lines = {row.po_line_id: row for row in procurement.po_lines}
    order_start = min((lines[row.po_line_id].order_date for row in scenario.scenario_truth_rows), default=earliest)
    start = min(add_months(earliest, -config.history_months_before_anchor), add_months(order_start, -1)).replace(day=1)
    return start, add_months(snapshot, config.future_months)
