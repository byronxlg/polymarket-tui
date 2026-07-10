"""Display formatters. Prices shown in cents to match the Polymarket web UI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polymarket_tui.models.market import Event, Market


def trunc(text: str, width: int) -> str:
    """Truncate with an ellipsis so cut-offs are visible."""
    text = text.strip()
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "…"


def error_brief(exc: object, width: int = 80) -> str:
    """A short, single-line description of an error for a status line.

    API errors embed the whole HTTP response body in their message: a 502's
    error_message is a multi-thousand-character HTML page. Dumping that into a
    one-line status field is useless, and its stray '[' broke Rich markup and
    crashed the app. Prefer a bare 'HTTP 502' when the exception carries a
    status code; otherwise the first line of the message, whitespace collapsed
    and truncated. (Rendering the result as a Text - not markup - is what
    actually prevents the crash; this just makes the line readable.)
    """
    status = getattr(exc, "status_code", None)
    if status:
        return f"HTTP {status}"
    # Prefer the exception's own message field over its repr: PolyApiException's
    # __str__ is "PolyApiException[status_code=..., error_message=...]", noise in
    # a status line. Fall back to str() for plain exceptions.
    msg = getattr(exc, "error_msg", None) or getattr(exc, "msg", None) or str(exc)
    raw = str(msg).strip()
    first = raw.splitlines()[0] if raw else exc.__class__.__name__
    return trunc(" ".join(first.split()), width)


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


def date_abs(dt: datetime | None) -> str:
    """Absolute short date for things in the past (resolution dates)."""
    if dt is None:
        return ""
    return f"{dt:%b} {dt.day} {dt.year}"


def ago(dt: datetime) -> str:
    """Compact 'time since' (12s / 5m / 3h / 2d) for activity timestamps."""
    if dt.tzinfo is None:
        # API timestamps are UTC; a naive parse must not TypeError the
        # aware-minus-naive subtraction below.
        dt = dt.replace(tzinfo=UTC)
    seconds = (datetime.now(UTC) - dt).total_seconds()
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.0f}h"
    return f"{seconds / 86400:.0f}d"


def market_status(market: Market) -> str:
    """One lifecycle token, three states.

    endDate is the *expected resolution* time, not a trading cutoff - the
    book stays live past it until the oracle resolves (api-reference.md).
    So: trading -> "ends <when>"; past endDate but open -> awaiting
    resolution; closed -> the resolution itself.
    """
    if market.closed:
        winner = market.winning_outcome
        when = date_abs(market.closed_time or market.end_date)
        if winner:
            return f"resolved - {winner} won {when}".rstrip()
        return f"closed {when}".rstrip()
    if market.end_date is not None and market.end_date < datetime.now(UTC):
        return "ended - awaiting resolution"
    if market.end_date is not None:
        return f"ends {end_date(market.end_date)}"
    return ""


def event_status(event: Event) -> str:
    """Event-level version of market_status (events carry no winner)."""
    if event.closed:
        return "closed"
    if event.end_date is not None and event.end_date < datetime.now(UTC):
        return "ended - awaiting resolution"
    if event.end_date is not None:
        return f"ends {end_date(event.end_date)}"
    return ""
