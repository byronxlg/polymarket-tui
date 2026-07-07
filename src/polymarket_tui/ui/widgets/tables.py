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
from polymarket_tui.ui.theme import AMBER, DOWN, UP
from polymarket_tui.ui.tiers import Tier
from polymarket_tui.ui.widgets.vim_table import VimDataTable


def pnl_text(cash: float, pct: float) -> Text:
    style = UP if cash > 0 else DOWN if cash < 0 else "dim"
    return Text(f"{cash:+,.2f} {pct:+.0f}%", style=style)


def pnl_text_stacked(cash: float, pct: float) -> Text:
    """Spacious rows: cash on the title line, percentage dim underneath."""
    style = UP if cash > 0 else DOWN if cash < 0 else "dim"
    out = Text(justify="right")
    out.append(f"{cash:+,.2f}", style=style)
    out.append(f"\n{pct:+.0f}%", style=f"dim {style}")
    return out


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

# Spacious positions re-compose the row (MS Teams comfy/compact model):
# outcome, size, and avg fold into a dim second line under the title, the
# percentage stacks under the cash P&L, and the freed width goes to titles.
POSITIONS_SPACIOUS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("market", "Market", 52),
        ("cur", "Cur", 7),
        ("value", "Value", 10),
        ("pnl", "P&L", 12),
    ),
    "medium": (
        ("market", "Market", 40),
        ("value", "Value", 10),
        ("pnl", "P&L", 12),
    ),
    "compact": (
        ("market", "Market", 26),
        ("pnl", "P&L", 12),
    ),
}


def position_meta(pos: Position) -> str:
    """The dim second line of a spacious position row: Yes · 1.2K sh · avg 33.4c."""
    return f"{pos.outcome} · {fmt.compact_size(pos.size)} sh · avg {fmt.cents(pos.avg_price)}"


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


def position_row(
    pos: Position,
    tier: Tier = "full",
    columns: list | None = None,
    density: str = "condensed",
    mark_won: bool = False,
) -> list:
    if columns is None:
        columns = (
            POSITIONS_SPACIOUS_TIER_COLUMNS[tier]
            if density == "spacious"
            else POSITIONS_TIER_COLUMNS[tier]
        )
    widths = {key: width for key, _, width in columns}
    # Narrow tiers drop the resolution-flag column; the row itself must
    # still say a resolved winner redeems (Byron, UX audit 2026-07-06).
    won = mark_won and pos.redeemable and pos.cur_price >= 0.5
    if density == "spacious":
        w = widths["market"]
        market = Text(fmt.trunc(pos.title, w))
        meta = position_meta(pos) + (" · won - redeem on web" if won else "")
        market.append("\n" + fmt.trunc(meta, w), style="dim")
        cells: dict[str, object] = {
            "market": market,
            "cur": fmt.cents(pos.cur_price),
            "value": fmt.money(pos.current_value),
            "pnl": pnl_text_stacked(pos.cash_pnl, pos.percent_pnl),
        }
    else:
        market = Text(fmt.trunc(pos.title, widths["market"] - (6 if won else 0)))
        if won:
            market.append(" (won)", style=AMBER)
        cells = {
            "market": market,
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
        # 1-wide B/S letter (the trades-rail idiom): a trade feed without
        # buy-vs-sell is unreadable, even as drill context.
        ("side", "S", 1),
        ("market", "Market", 22),
        ("usdc", "USDC", 10),
    ),
}

# Spacious activity re-composes the row the same way positions do: the
# when/type/side/outcome/price/size columns fold into a dim second line
# under the market title and the freed width goes to full titles. USDC (the
# trade's notional - the money) stays as its own column.
ACTIVITY_SPACIOUS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("market", "Market", 56),
        ("usdc", "USDC", 10),
    ),
    "medium": (
        ("market", "Market", 42),
        ("usdc", "USDC", 10),
    ),
    "compact": (
        ("market", "Market", 28),
        ("usdc", "USDC", 10),
    ),
}


def activity_meta(item: ActivityItem) -> str:
    """The dim second line of a spacious activity row:
    Jul 05 14:32 · BUY Yes @ 33.4c · 1.2K sh.

    Buy/sell is muted here (design principle: side reads secondary to the
    outcome); the notional stays in the USDC column beside it."""
    when = item.when.astimezone().strftime("%b %d %H:%M")
    action = item.side or item.type  # TRADE rows carry BUY/SELL; others their type
    label = f"{action} {item.outcome}".strip() if item.outcome else action
    if item.type == "TRADE" and item.price:
        label += f" @ {fmt.cents(item.price)}"
    parts = [when, label]
    if item.size:
        parts.append(f"{fmt.compact_size(item.size)} sh")
    return " · ".join(p for p in parts if p)


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
    density: str = "condensed",
) -> list:
    if columns is None:
        columns = (
            ACTIVITY_SPACIOUS_TIER_COLUMNS[tier]
            if density == "spacious"
            else _activity_full_columns(market_width, 10)
            if tier == "full"
            else ACTIVITY_TIER_COLUMNS[tier]
        )
    widths = {key: width for key, _, width in columns}
    if density == "spacious":
        w = widths["market"]
        market = Text(fmt.trunc(item.title, w))
        market.append("\n" + fmt.trunc(activity_meta(item), w), style="dim")
        cells = {"market": market, "usdc": fmt.money(item.usdc_size)}
        return [cells[key] for key, _, _ in columns]
    if not item.size:
        size = "-"
    elif compact_size:
        size = fmt.compact_size(item.size)
    else:
        size = f"{item.size:,.0f}"
    cells = {
        "when": item.when.astimezone().strftime("%b %d %H:%M"),
        "type": item.type,
        # A 1-wide compact column shows the B/S letter, wider tiers the word.
        "side": Text(
            item.side[:1] if widths.get("side", 5) <= 2 else item.side,
            style=UP if item.side == "BUY" else DOWN,
        )
        if item.side
        else "-",
        "market": fmt.trunc(item.title, widths["market"]),
        "outcome": fmt.trunc(item.outcome, widths.get("outcome", 10)),
        "price": fmt.cents(item.price) if item.type == "TRADE" else "-",
        "size": size,
        "usdc": fmt.money(item.usdc_size),
    }
    return [cells[key] for key, _, _ in columns]
