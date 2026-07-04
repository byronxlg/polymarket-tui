"""Shared table configuration for positions (portfolio screen + trader profiles)."""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import Position
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
