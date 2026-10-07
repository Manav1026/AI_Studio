"""Resolve SOQL date literals into concrete date ranges (used by the mock connector and tests)."""
from datetime import date, timedelta


def _quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


def date_literal_range(name: str, n: int | None, today: date) -> tuple[date, date]:
    name = name.upper().replace("_FISCAL", "")
    if name == "TODAY":
        return today, today
    if name == "YESTERDAY":
        d = today - timedelta(days=1)
        return d, d
    if name == "TOMORROW":
        d = today + timedelta(days=1)
        return d, d
    week_start = today - timedelta(days=(today.weekday() + 1) % 7)  # Sunday-start weeks
    if name in ("THIS_WEEK", "LAST_WEEK", "NEXT_WEEK"):
        off = {"THIS_WEEK": 0, "LAST_WEEK": -7, "NEXT_WEEK": 7}[name]
        s = week_start + timedelta(days=off)
        return s, s + timedelta(days=6)
    month_start = today.replace(day=1)
    if name in ("THIS_MONTH", "LAST_MONTH", "NEXT_MONTH"):
        s = _add_months(month_start, {"THIS_MONTH": 0, "LAST_MONTH": -1, "NEXT_MONTH": 1}[name])
        return s, _add_months(s, 1) - timedelta(days=1)
    q = _quarter_start(today)
    if name in ("THIS_QUARTER", "LAST_QUARTER", "NEXT_QUARTER"):
        s = _add_months(q, {"THIS_QUARTER": 0, "LAST_QUARTER": -3, "NEXT_QUARTER": 3}[name])
        return s, _add_months(s, 3) - timedelta(days=1)
    if name in ("THIS_YEAR", "LAST_YEAR", "NEXT_YEAR"):
        y = today.year + {"THIS_YEAR": 0, "LAST_YEAR": -1, "NEXT_YEAR": 1}[name]
        return date(y, 1, 1), date(y, 12, 31)
    if name == "LAST_90_DAYS":
        return today - timedelta(days=90), today
    if name == "NEXT_90_DAYS":
        return today, today + timedelta(days=90)
    n = n or 0
    if name == "LAST_N_DAYS":
        return today - timedelta(days=n), today
    if name == "NEXT_N_DAYS":
        return today, today + timedelta(days=n)
    if name == "LAST_N_WEEKS":
        return week_start - timedelta(days=7 * n), week_start - timedelta(days=1)
    if name == "NEXT_N_WEEKS":
        s = week_start + timedelta(days=7)
        return s, s + timedelta(days=7 * n - 1)
    if name == "LAST_N_MONTHS":
        return _add_months(month_start, -n), month_start - timedelta(days=1)
    if name == "NEXT_N_MONTHS":
        s = _add_months(month_start, 1)
        return s, _add_months(s, n) - timedelta(days=1)
    if name == "LAST_N_QUARTERS":
        return _add_months(q, -3 * n), q - timedelta(days=1)
    if name == "NEXT_N_QUARTERS":
        s = _add_months(q, 3)
        return s, _add_months(s, 3 * n) - timedelta(days=1)
    if name == "LAST_N_YEARS":
        return date(today.year - n, 1, 1), date(today.year - 1, 12, 31)
    if name == "NEXT_N_YEARS":
        return date(today.year + 1, 1, 1), date(today.year + n, 12, 31)
    raise ValueError(f"Unsupported date literal {name}")
