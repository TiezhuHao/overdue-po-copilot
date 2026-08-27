from datetime import date
from decimal import Decimal


def overdue_days(snapshot_date: date, order_date: date, material_lt_days: int) -> int:
    return (snapshot_date - order_date).days - material_lt_days - 240


def is_overdue(snapshot_date: date, order_date: date, material_lt_days: int) -> bool:
    return overdue_days(snapshot_date, order_date, material_lt_days) > 0


def overdue_open_qty(schedule_qty: Decimal, schedule_received_qty: Decimal) -> Decimal:
    return max(schedule_qty - schedule_received_qty, Decimal("0"))
