"""Shared table configuration for positions and activity (portfolio + trader profiles)."""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import ActivityItem, Position
from polymarket_tui.ui.widgets.vim_table import VimDataTable


def pnl_text(cash: float, pct: float) -> Text:
    style = "green" if cash > 0 else "red" if cash < 0 else "dim"
    return Text(f"{cash:+,.2f} {pct:+.0f}%", style=style)


def setup_positions_columns(table: VimDataTable, flag_column: bool = False) -> None:
    table.add_column("Market", width=44, key="market")
    table.add_column("Outcome", width=12, key="outcome")
    table.add_column("Size", width=9, key="size")
    table.add_column("Avg", width=7, key="avg")
    table.add_column("Cur", width=7, key="cur")
    table.add_column("Value", width=10, key="value")
    table.add_column("P&L", width=16, key="pnl")
    if flag_column:
        table.add_column("", width=20, key="flag")


def position_row(pos: Position) -> list:
    return [
        fmt.trunc(pos.title, 44),
        fmt.trunc(pos.outcome, 12),
        fmt.compact_size(pos.size),
        fmt.cents(pos.avg_price),
        fmt.cents(pos.cur_price),
        fmt.money(pos.current_value),
        pnl_text(pos.cash_pnl, pos.percent_pnl),
    ]


def setup_activity_columns(
    table: VimDataTable, *, market_width: int = 46, size_width: int = 10
) -> None:
    """Columns for a trade/activity history table (portfolio History, trader Activity)."""
    table.add_column("When", width=13, key="when")
    table.add_column("Type", width=8, key="type")
    table.add_column("Side", width=5, key="side")
    table.add_column("Market", width=market_width, key="market")
    table.add_column("Outcome", width=10, key="outcome")
    table.add_column("Price", width=7, key="price")
    table.add_column("Size", width=size_width, key="size")
    table.add_column("USDC", width=10, key="usdc")


def activity_row(item: ActivityItem, *, market_width: int = 46, compact_size: bool = True) -> list:
    if not item.size:
        size = "-"
    elif compact_size:
        size = fmt.compact_size(item.size)
    else:
        size = f"{item.size:,.0f}"
    return [
        item.when.astimezone().strftime("%b %d %H:%M"),
        item.type,
        Text(item.side, style="green" if item.side == "BUY" else "red") if item.side else "-",
        fmt.trunc(item.title, market_width),
        fmt.trunc(item.outcome, 10),
        fmt.cents(item.price) if item.type == "TRADE" else "-",
        size,
        fmt.money(item.usdc_size),
    ]
