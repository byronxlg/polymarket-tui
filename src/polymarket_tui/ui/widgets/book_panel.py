"""Order book rendering: top N levels per side with size bars.

The panel is focusable: up/down move a cursor through the price levels and
the hovered level is highlighted. The market screen reads the hovered price
to pre-fill an order (space buys at the level under the cursor). Up past the
top level raises CursorExitedTop so focus can step back to the outcome table.
"""

from __future__ import annotations

import math

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import BookLevel, OrderBook
from polymarket_tui.ui.theme import AMBER, DOWN, UP

DEPTH = 10
# Solid block bars at full red/green glare; the fill stays muted while the
# price/size text keeps the strong side color.
ASK_BAR = "rgb(125,52,47)"
BID_BAR = "rgb(42,104,64)"
MIN_BAR_WIDTH = 12
MAX_BAR_WIDTH = 60
FIXED_COLS = 24  # " price(7) shares(10)" + spacing + own-order marker


class BookPanel(Static):
    can_focus = True

    BINDINGS = [
        Binding("up", "cursor_up", "up", show=False),
        Binding("down", "cursor_down", "down", show=False),
        Binding("left", "app.nav_back", "back", show=False),
    ]

    class CursorExitedTop(Message):
        """Up pressed on the top book level - step focus back above."""

        def __init__(self, panel: BookPanel) -> None:
            super().__init__()
            self.panel = panel

    def __init__(self, **kwargs) -> None:
        super().__init__("loading book...", **kwargs)
        self._own_prices: set[float] = set()
        self._book: OrderBook | None = None
        # Display-order levels (highest ask down to lowest bid) with their side.
        self._levels: list[tuple[BookLevel, str]] = []
        # Cursor tracked by price, not index: a live book rebuilds constantly,
        # so an index would jump under the cursor while a price stays put.
        self._cursor_price: float | None = None

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

    def on_focus(self) -> None:
        if self._cursor_price is None and self._levels:
            self._cursor_price = self._levels[0][0].price
        self._rerender()

    def on_blur(self) -> None:
        self._rerender()

    def show_error(self, message: str) -> None:
        self._book = None
        self._levels = []
        self.update(Text(message, style="dim"))

    # -- cursor -----------------------------------------------------------------

    def _cursor_index(self) -> int | None:
        if self._cursor_price is None:
            return None
        for i, (level, _side) in enumerate(self._levels):
            if abs(level.price - self._cursor_price) < 1e-9:
                return i
        return None

    def selected_price(self) -> float | None:
        """Price of the level under the cursor (dollars, 0-1), or None."""
        idx = self._cursor_index()
        return self._levels[idx][0].price if idx is not None else None

    def action_cursor_up(self) -> None:
        idx = self._cursor_index()
        if not self._levels:
            return
        if idx is None:
            self._cursor_price = self._levels[0][0].price
        elif idx == 0:
            self.post_message(self.CursorExitedTop(self))
            return
        else:
            self._cursor_price = self._levels[idx - 1][0].price
        self._rerender()

    def action_cursor_down(self) -> None:
        idx = self._cursor_index()
        if not self._levels:
            return
        if idx is None:
            self._cursor_price = self._levels[0][0].price
        elif idx < len(self._levels) - 1:
            self._cursor_price = self._levels[idx + 1][0].price
        self._rerender()

    def _bar_width(self) -> int:
        width = self.size.width or (MIN_BAR_WIDTH + FIXED_COLS + 2)
        return max(MIN_BAR_WIDTH, min(MAX_BAR_WIDTH, width - FIXED_COLS))

    def _level_line(
        self,
        level: BookLevel,
        max_size: float,
        style: str,
        bar_style: str,
        bar_w: int,
        selected: bool,
    ) -> Text:
        # log scale so one whale level doesn't flatten every other bar to nothing
        filled = 0
        if max_size > 0 and level.size > 0:
            ratio = math.log10(1 + level.size) / math.log10(1 + max_size)
            filled = max(1, int(round(bar_w * ratio)))
        # Selected row: explicit highlight background reads reliably in Textual
        # (Rich `reverse` on a Static does not composite to a visible swap). The
        # bar keeps its muted fill; the price keeps the strong side color.
        hi = " on rgb(38,64,102)" if selected else ""
        bar = f"bold {bar_style}{hi}" if selected else bar_style
        text = f"bold {style}{hi}" if selected else style
        line = Text()
        line.append(" " * (bar_w - filled), style=hi.strip() or None)
        line.append("█" * filled, style=bar)
        line.append(f" {fmt.cents(level.price):>7}", style=text)
        line.append(f" {fmt.compact_size(level.size):>10}", style=hi.strip() or None)
        if any(abs(level.price - p) < 1e-9 for p in self._own_prices):
            line.append(" *", style=f"bold {AMBER}")
        line.append("\n")
        return line

    def _rerender(self) -> None:
        if self._book is not None:
            self.update_book(self._book)

    def update_book(self, book: OrderBook) -> None:
        self._book = book
        bar_w = self._bar_width()
        asks = sorted(book.asks, key=lambda lvl: lvl.price)[:DEPTH]
        bids = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)[:DEPTH]
        max_size = max((lvl.size for lvl in asks + bids), default=0.0)

        # Display order (top to bottom) with side; the cursor rides this list.
        self._levels = [(lvl, "ask") for lvl in reversed(asks)] + [(lvl, "bid") for lvl in bids]
        cursor_idx = self._cursor_index() if self.has_focus else None

        out = Text()
        out.append(f"{'':>{bar_w}} {'price':>7} {'shares':>10}\n", style="bold dim")

        row = 0
        for level in reversed(asks):
            out.append_text(
                self._level_line(level, max_size, DOWN, ASK_BAR, bar_w, row == cursor_idx)
            )
            row += 1

        if book.midpoint is not None:
            out.append(
                f"---- mid {fmt.cents(book.midpoint)}  spread {fmt.cents(book.spread)} ----\n",
                style=f"bold {AMBER}",
            )
        elif not asks and not bids:
            out.append("empty book\n", style="dim")

        for level in bids:
            out.append_text(
                self._level_line(level, max_size, UP, BID_BAR, bar_w, row == cursor_idx)
            )
            row += 1

        self.update(out)
