"""Display formatters. Prices shown in cents to match the Polymarket web UI."""

from __future__ import annotations

from datetime import UTC, datetime


def trunc(text: str, width: int) -> str:
    """Truncate with an ellipsis so cut-offs are visible."""
    text = text.strip()
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "…"


def cents(price: float | None, signed: bool = False) -> str:
    if price is None:
        return "-"
    c = price * 100
    if signed:
        return f"{c:+.1f}c"
    return f"{c:.1f}c"


def cents_exact(price: float | None) -> str:
    """Cents keeping sub-tenth precision (own-order fills/toasts): a 33.45c
    fill must not read as 33.4c. Trailing zeros trimmed to one place."""
    if price is None:
        return "-"
    text = f"{price * 100:.2f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return text + "c"


def money(value: float | None) -> str:
    if value is None:
        return "-"
    a = abs(value)
    if a >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if a >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if a >= 10_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.2f}"


def vol(value: float | None) -> str:
    """Compact dollars for volume/liquidity columns: $475, $6.9K, $54K, $3.6M.

    Unlike money(), never shows cents - flow columns are read for magnitude,
    and mixing $475.37 with $54K in one column reads as two formats.
    """
    if value is None:
        return "-"
    a = abs(value)
    if a >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if a >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if a >= 10_000:
        return f"${value / 1_000:.0f}K"
    if a >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def compact_size(size: float) -> str:
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f}M"
    if size >= 10_000:
        return f"{size / 1_000:.0f}K"
    if size >= 1_000:
        return f"{size / 1_000:.1f}K"
    return f"{size:,.0f}"


def end_date(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    now = datetime.now(UTC)
    delta = dt - now
    if delta.days < 0:
        return "ended"
    if delta.days == 0:
        hours = delta.seconds // 3600
        return f"{hours}h" if hours else f"{delta.seconds // 60}m"
    if delta.days < 365:
        return dt.strftime("%b %d")
    return dt.strftime("%b %Y")
