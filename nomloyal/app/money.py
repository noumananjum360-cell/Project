"""Money is stored as integer minor units (paisa / cents) - never as floats."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY = {"code": "PKR", "symbol": "Rs"}


def to_minor(value) -> int:
    """'1,250.50' / 1250.5 / Decimal -> 125050. Raises ValueError for invalid or negative input."""
    if isinstance(value, int) and not isinstance(value, bool):
        raise TypeError("pass major units as str/float/Decimal; ints are ambiguous")
    try:
        d = Decimal(str(value).replace(",", "").strip() or "0")
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' is not a valid amount") from exc
    if d < 0:
        raise ValueError("Amounts cannot be negative")
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor(minor: int) -> Decimal:
    return (Decimal(int(minor)) / 100).quantize(Decimal("0.01"))


def fmt(minor: int | None, symbol: bool = True) -> str:
    if minor is None:
        return "-"
    neg = minor < 0
    d = from_minor(abs(minor))
    s = f"{d:,.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    s = ("-" if neg else "") + s
    return f"{CURRENCY['symbol']} {s}" if symbol else s


def pct_of(amount_minor: int, rate_bp: int) -> int:
    """amount * rate (basis points, 1700 = 17%), rounded half-up to the minor unit."""
    return int((Decimal(amount_minor) * Decimal(rate_bp) / Decimal(10000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rate_bp(text) -> int:
    """'17' or '17.5' (percent) -> 1700 / 1750 basis points."""
    try:
        d = Decimal(str(text).replace("%", "").strip() or "0")
    except InvalidOperation as exc:
        raise ValueError(f"'{text}' is not a valid percentage") from exc
    if d < 0 or d > 100:
        raise ValueError("Percentage must be between 0 and 100")
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fmt_rate(bp: int | None) -> str:
    if bp is None:
        return "-"
    d = Decimal(bp) / 100
    return f"{d.normalize():f}%"
