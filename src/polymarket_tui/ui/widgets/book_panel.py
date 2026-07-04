"""Order book rendering: top N levels per side with size bars."""

from __future__ import annotations

import math

from rich.text import Text
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import BookLevel, OrderBook

DEPTH = 10
MIN_BAR_WIDTH = 12
MAX_BAR_WIDTH = 60
FIXED_COLS = 24  # " price(7) shares(10)" + spacing + own-order marker


class BookPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("loading book...", **kwargs)
        self._own_prices: set[float] = set()
        self._book: OrderBook | None = None

    def set_own_prices(self, prices: set[float]) -> None:
        """Price levels holding one of your resting orders (marked with *)."""
        if prices != self._own_prices:
            self._own_prices = set(prices)
            if self._book is not None:
                self.update_book(self._book)

    def on_resize(self) -> None:
        # Bars stretch to the measured width - re-render on change.
        if self._book is not None:
            self.update_book(self._book)

    def show_error(self, message: str) -> None:
        self.update(Text(message, style="dim"))

    def _bar_width(self) -> int:
        width = self.size.width or (MIN_BAR_WIDTH + FIXED_COLS + 2)
        return max(MIN_BAR_WIDTH, min(MAX_BAR_WIDTH, width - FIXED_COLS))

    def _level_line(self, level: BookLevel, max_size: float, style: str, bar_w: int) -> Text:
        # log scale so one whale level doesn't flatten every other bar to nothing
        filled = 0
        if max_size > 0 and level.size > 0:
            ratio = math.log10(1 + level.size) / math.log10(1 + max_size)
            filled = max(1, int(round(bar_w * ratio)))
        line = Text()
        line.append(" " * (bar_w - filled))
        line.append("\u2588" * filled, style=style)
        line.append(f" {fmt.cents(level.price):>7}", style=style)
        line.append(f" {fmt.compact_size(level.size):>10}")
        if any(abs(level.price - p) < 1e-9 for p in self._own_prices):
            line.append(" *", style="bold yellow")
        line.append("\n")
        return line

    def update_book(self, book: OrderBook) -> None:
        self._book = book
        bar_w = self._bar_width()
        asks = sorted(book.asks, key=lambda lvl: lvl.price)[:DEPTH]
        bids = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)[:DEPTH]
        max_size = max((lvl.size for lvl in asks + bids), default=0.0)

        out = Text()
        out.append(f"{'':>{bar_w}} {'price':>7} {'shares':>10}\n", style="bold dim")

        for level in reversed(asks):
            out.append_text(self._level_line(level, max_size, "red", bar_w))

        if book.midpoint is not None:
            out.append(
                f"---- mid {fmt.cents(book.midpoint)}  spread {fmt.cents(book.spread)} ----\n",
                style="bold yellow",
            )
        elif not asks and not bids:
            out.append("empty book\n", style="dim")

        for level in bids:
            out.append_text(self._level_line(level, max_size, "green", bar_w))

        self.update(out)
