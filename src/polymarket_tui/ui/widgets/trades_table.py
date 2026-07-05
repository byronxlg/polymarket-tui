"""Live trades table: thin-rail and expanded column presets.

Rows are keyed "address|name" so screens can open the trader's profile from
a selected row.
"""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import ActivityItem
from polymarket_tui.ui.theme import DOWN, UP
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class TradesTable(VimDataTable):
    def __init__(self, compact: bool = True, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.compact = compact

    def on_mount(self) -> None:
        self.build_columns()

    def build_columns(self) -> None:
        self.clear(columns=True)
        self.add_column("Time", width=8, key="time")
        self.add_column("S", width=1 if self.compact else 4, key="side")
        self.add_column("Size", width=7, key="size")
        self.add_column("Price", width=6, key="price")
        if not self.compact:
            self.add_column("USDC", width=9, key="usdc")
            self.add_column("Trader", width=24, key="trader")

    def set_trades(self, trades: list[ActivityItem]) -> None:
        self.clear()
        for i, trade in enumerate(trades):
            side_char = trade.side[:1] if self.compact else trade.side
            side_text = Text(side_char, style=UP if trade.side == "BUY" else DOWN)
            row = [
                trade.when.astimezone().strftime("%H:%M:%S"),
                side_text,
                fmt.compact_size(trade.size),
                fmt.cents(trade.price),
            ]
            if not self.compact:
                row.append(fmt.money(trade.usdc_size) if trade.usdc_size else "-")
                row.append(fmt.trunc(trade.trader, 24))
            self.add_row(*row, key=f"{i}|{trade.proxy_wallet}|{trade.trader}")
        if trades:
            self.move_cursor(row=0)

    def trader_at_cursor(self) -> tuple[str, str] | None:
        """(address, display name) of the highlighted trade's trader."""
        if self.cursor_row is None or self.row_count == 0:
            return None
        key = str(self.coordinate_to_cell_key((self.cursor_row, 0)).row_key.value)
        parts = key.split("|", 2)
        if len(parts) < 3 or not parts[1]:
            return None
        return parts[1], parts[2]
