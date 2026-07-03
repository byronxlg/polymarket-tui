"""Order book rendering: top N levels per side with size bars."""

from __future__ import annotations

import math

from rich.text import Text
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import BookLevel, OrderBook

DEPTH = 10
BAR_WIDTH = 14


class BookPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("loading book...", **kwargs)

    def show_error(self, message: str) -> None:
        self.update(Text(message, style="dim"))

    def _level_line(self, level: BookLevel, max_size: float, style: str) -> Text:
        # log scale so one whale level doesn't flatten every other bar to nothing
        filled = 0
        if max_size > 0 and level.size > 0:
            ratio = math.log10(1 + level.size) / math.log10(1 + max_size)
            filled = max(1, int(round(BAR_WIDTH * ratio)))
        line = Text()
        line.append(" " * (BAR_WIDTH - filled))
        line.append("#" * filled, style=style)
        line.append(f" {fmt.cents(level.price):>7}", style=style)
        line.append(f" {fmt.compact_size(level.size):>10}\n")
        return line

    def update_book(self, book: OrderBook) -> None:
        asks = sorted(book.asks, key=lambda lvl: lvl.price)[:DEPTH]
        bids = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)[:DEPTH]
        max_size = max((lvl.size for lvl in asks + bids), default=0.0)

        out = Text()
        out.append(f"{'':>{BAR_WIDTH}} {'price':>7} {'shares':>10}\n", style="bold dim")

        for level in reversed(asks):
            out.append_text(self._level_line(level, max_size, "red"))

        if book.midpoint is not None:
            out.append(
                f"---- mid {fmt.cents(book.midpoint)}  spread {fmt.cents(book.spread)} ----\n",
                style="bold yellow",
            )
        elif not asks and not bids:
            out.append("empty book\n", style="dim")

        for level in bids:
            out.append_text(self._level_line(level, max_size, "green"))

        self.update(out)
