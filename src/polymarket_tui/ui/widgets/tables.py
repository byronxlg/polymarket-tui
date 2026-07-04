"""Shared table configuration for positions and activity (portfolio + trader profiles).

Column sets are tier-aware (see ui.tiers): "full" keeps the historical
layout (with the width knobs the portfolio screen passes), "medium" and
"compact" drop the lowest-value columns so drill panes at 70%/30% width
never clip.
"""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import ActivityItem, Position
from polymarket_tui.ui.tiers import Tier
from polymarket_tui.ui.widgets.vim_table import VimDataTable


def pnl_text(cash: float, pct: float) -> Text:
    style = "green" if cash > 0 else "red" if cash < 0 else "dim"
    return Text(f"{cash:+,.2f} {pct:+.0f}%", style=style)


# (key, label, width) per width tier. "full" is defined in the setup
# functions because its widths are parameterized by the caller.
POSITIONS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("market", "Market", 44),
        ("outcome", "Outcome", 12),
        ("size", "Size", 9),
        ("avg", "Avg", 7),
        ("cur", "Cur", 7),
        ("value", "Value", 10),
        ("pnl", "P&L", 16),
    ),
    "medium": (
        ("market", "Market", 36),
        ("outcome", "Outcome", 10),
        ("size", "Size", 9),
        ("value", "Value", 10),
        ("pnl", "P&L", 16),
    ),
    "compact": (
        ("market", "Market", 26),
        ("value", "Value", 10),
        ("pnl", "P&L", 13),
    ),
}


def setup_positions_columns(
    table: VimDataTable,
    flag_column: bool = False,
    tier: Tier = "full",
    columns: list | None = None,
) -> None:
    for key, label, width in columns or POSITIONS_TIER_COLUMNS[tier]:
        table.add_column(label, width=width, key=key)
    if flag_column and tier == "full":
        table.add_column("", width=20, key="flag")


def position_row(pos: Position, tier: Tier = "full", columns: list | None = None) -> list:
    columns = columns or POSITIONS_TIER_COLUMNS[tier]
    widths = {key: width for key, _, width in columns}
    cells = {
        "market": fmt.trunc(pos.title, widths["market"]),
        "outcome": fmt.trunc(pos.outcome, widths.get("outcome", 12)),
        "size": fmt.compact_size(pos.size),
        "avg": fmt.cents(pos.avg_price),
        "cur": fmt.cents(pos.cur_price),
        "value": fmt.money(pos.current_value),
        "pnl": pnl_text(pos.cash_pnl, pos.percent_pnl),
    }
    return [cells[key] for key, _, _ in columns]


def _activity_full_columns(market_width: int, size_width: int) -> tuple:
    return (
        ("when", "When", 13),
        ("type", "Type", 8),
        ("side", "Side", 5),
        ("market", "Market", market_width),
        ("outcome", "Outcome", 10),
        ("price", "Price", 7),
        ("size", "Size", size_width),
        ("usdc", "USDC", 10),
    )


ACTIVITY_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": _activity_full_columns(46, 10),
    "medium": (
        ("when", "When", 13),
        ("side", "Side", 5),
        ("market", "Market", 34),
        ("price", "Price", 7),
        ("size", "Size", 8),
        ("usdc", "USDC", 10),
    ),
    "compact": (
        ("when", "When", 13),
        ("market", "Market", 22),
        ("usdc", "USDC", 10),
    ),
}


def setup_activity_columns(
    table: VimDataTable,
    *,
    market_width: int = 46,
    size_width: int = 10,
    tier: Tier = "full",
    columns: list | None = None,
) -> None:
    """Columns for a trade/activity history table (portfolio History, trader Activity)."""
    if columns is None:
        columns = (
            _activity_full_columns(market_width, size_width)
            if tier == "full"
            else ACTIVITY_TIER_COLUMNS[tier]
        )
    for key, label, width in columns:
        table.add_column(label, width=width, key=key)


def activity_row(
    item: ActivityItem,
    *,
    market_width: int = 46,
    compact_size: bool = True,
    tier: Tier = "full",
    columns: list | None = None,
) -> list:
    if columns is None:
        columns = (
            _activity_full_columns(market_width, 10)
            if tier == "full"
            else ACTIVITY_TIER_COLUMNS[tier]
        )
    widths = {key: width for key, _, width in columns}
    if not item.size:
        size = "-"
    elif compact_size:
        size = fmt.compact_size(item.size)
    else:
        size = f"{item.size:,.0f}"
    cells = {
        "when": item.when.astimezone().strftime("%b %d %H:%M"),
        "type": item.type,
        "side": Text(item.side, style="green" if item.side == "BUY" else "red")
        if item.side
        else "-",
        "market": fmt.trunc(item.title, widths["market"]),
        "outcome": fmt.trunc(item.outcome, widths.get("outcome", 10)),
        "price": fmt.cents(item.price) if item.type == "TRADE" else "-",
        "size": size,
        "usdc": fmt.money(item.usdc_size),
    }
    return [cells[key] for key, _, _ in columns]
