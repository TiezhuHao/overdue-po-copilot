from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.procurement import is_overdue, overdue_days, overdue_open_qty


def test_at_014_and_at_015_overdue_formula_and_strict_boundary() -> None:
    snapshot = date(2026, 8, 26)
    lt_days = 30
    threshold_order_date = snapshot - timedelta(days=lt_days + 240)
    assert overdue_days(snapshot, threshold_order_date, lt_days) == 0
    assert is_overdue(snapshot, threshold_order_date, lt_days) is False
    assert overdue_days(snapshot, threshold_order_date - timedelta(days=1), lt_days) == 1
    assert is_overdue(snapshot, threshold_order_date - timedelta(days=1), lt_days) is True
    assert overdue_days(snapshot, threshold_order_date + timedelta(days=1), lt_days) == -1


def test_at_016_due_date_is_not_an_input() -> None:
    snapshot = date(2026, 8, 26)
    assert is_overdue(snapshot, date(2025, 8, 1), 30)
    assert not is_overdue(snapshot, date(2026, 8, 1), 30)


def test_at_017_schedule_level_open_quantity() -> None:
    assert overdue_open_qty(Decimal("100"), Decimal("40")) == Decimal("60")
    assert overdue_open_qty(Decimal("10"), Decimal("10")) == Decimal("0")


def test_at_019_procurement_logic_has_no_machine_business_date() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            root / "domain" / "procurement" / "overdue.py",
            root / "generators" / "procurement" / "generator.py",
            root / "generators" / "procurement" / "validation.py",
        ]
    )
    assert "date.today(" not in text
    assert "datetime.now(" not in text
