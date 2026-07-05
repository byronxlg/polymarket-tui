"""Order book rendering: top N levels per side with size bars.

Focusable and cursor-navigable (issue: cursor through the book from the outcome
table). Down from the outcome table lands here; up/down move a row cursor;
up-at-top or left steps back to the outcome table. `space` is the contextual
buy/sell - it opens the order panel prefilled from the selected level (take an
ask => BUY, hit a bid => SELL, price and size from that level). `x` cancels your
resting order(s) at the selected level. Both are posted as messages; MarketPane
owns the order panel and the cancel flow.
"""

from __future__ import annotations

import math

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import BookLevel, OrderBook
from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.ui.theme import AMBER, DOWN, UP

DEPTH = 10
# Solid block bars at full red/green glare; the fill stays muted while the
# price/size text keeps the strong side color.
ASK_BAR = "rgb(125,52,47)"
BID_BAR = "rgb(42,104,64)"
MIN_BAR_WIDTH = 12
MAX_BAR_WIDTH = 60
FIXED_COLS = 24  # " price(7) shares(10)" + spacing + own-order marker
# The cursor row uses the same highlight as every DataTable in the app
# (app.tcss: .datatable--cursor = $primary 25%): BLUE #5b8ef7 at 25% over the
# navy surface #0d1320 resolves to this flat tint.
CURSOR_BG = "#213256"


class BookPanel(Static):
    can_focus = True

    BINDINGS = [
        Binding("up", "cursor(-1)", "up", show=False),
        Binding("down", "cursor(1)", "down", show=False),
        Binding("space", "order_here", "order", show=True),
        Binding("x", "cancel_here", "cancel", show=True),
        Binding("left", "focus_above", "back", show=False),
    ]

    class RowActioned(Message):
        """space on a level: open an order prefilled from it (side by book side)."""

        def __init__(self, side: str, price: float, size: float) -> None:
            super().__init__()
            self.side = side  # "BUY" on an ask, "SELL" on a bid
            self.price = price
            self.size = size

    class CancelRequested(Message):
        """x on a level: cancel the resting order(s) there (empty if none)."""

        def __init__(self, orders: list[OpenOrder]) -> None:
            super().__init__()
            self.orders = orders

    class FocusAbove(Message):
        """up-at-top / left: hand focus back to the outcome table."""

    class CursorMoved(Message):
        """Cursor changed row - lets the pane drop a stale armed cancel."""

    def __init__(self, **kwargs) -> None:
        super().__init__("loading book...", **kwargs)
        self._own_orders: list[OpenOrder] = []
        self._book: OrderBook | None = None
        self._levels: list[tuple[str, BookLevel]] = []  # display order: asks then bids
        self._cursor = 0

    # -- state ------------------------------------------------------------------

    @property
    def has_levels(self) -> bool:
        return bool(self._levels)

    def focus_top(self) -> None:
        """Enter the book at its top row (called when arrowing down into it)."""
        self._cursor = 0

    def set_own_orders(self, orders: list[OpenOrder]) -> None:
        """Your resting orders on this token: star their levels and enable x."""
        self._own_orders = list(orders)
        if self._book is not None:
            self._render_book()

    def _orders_at(self, price: float) -> list[OpenOrder]:
        return [o for o in self._own_orders if abs(o.price - price) < 1e-9]

    def on_resize(self) -> None:
        # Bars stretch to the measured width - re-render on change.
        if self._book is not None:
            self._render_book()

    def on_focus(self) -> None:
        if self._book is not None:
            self._render_book()

    def on_blur(self) -> None:
        if self._book is not None:
            self._render_book()

    def show_error(self, message: str) -> None:
        self._book = None
        self._levels = []
        self.update(Text(message, style="dim"))

    # -- actions ----------------------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        if not self._levels:
            if delta < 0:
                self.post_message(self.FocusAbove())
            return
        target = self._cursor + delta
        if target < 0:
            self.post_message(self.FocusAbove())
            return
        if target >= len(self._levels):
            return  # clamp at the last row
        self._cursor = target
        self.post_message(self.CursorMoved())
        self._render_book()

    def action_focus_above(self) -> None:
        self.post_message(self.FocusAbove())

    def action_order_here(self) -> None:
        if not (self.has_focus and self._levels):
            return
        side_kind, level = self._levels[self._cursor]
        side = "BUY" if side_kind == "ask" else "SELL"
        self.post_message(self.RowActioned(side, level.price, level.size))

    def action_cancel_here(self) -> None:
        if not (self.has_focus and self._levels):
            return
        _, level = self._levels[self._cursor]
        self.post_message(self.CancelRequested(self._orders_at(level.price)))

    # -- rendering --------------------------------------------------------------

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
        cursor: bool,
    ) -> Text:
        # log scale so one whale level doesn't flatten every other bar to nothing
        filled = 0
        if max_size > 0 and level.size > 0:
            ratio = math.log10(1 + level.size) / math.log10(1 + max_size)
            filled = max(1, int(round(bar_w * ratio)))
        line = Text()
        line.append(" " * (bar_w - filled))
        line.append("█" * filled, style=bar_style)
        line.append(f" {fmt.cents(level.price):>7}", style=style)
        line.append(f" {fmt.compact_size(level.size):>10}")
        if self._orders_at(level.price):
            line.append(" *", style=f"bold {AMBER}")
        if cursor:
            # Same treatment as the DataTable row cursor: a full-width tint,
            # text keeps its side color. Pad so the highlight spans the row.
            pad = self.size.width - line.cell_len
            if pad > 0:
                line.append(" " * pad)
            line.stylize(f"on {CURSOR_BG}")
        line.append("\n")
        return line

    def update_book(self, book: OrderBook) -> None:
        self._book = book
        self._render_book()

    def _render_book(self) -> None:
        book = self._book
        if book is None:
            return
        bar_w = self._bar_width()
        asks = sorted(book.asks, key=lambda lvl: lvl.price)[:DEPTH]
        bids = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)[:DEPTH]
        max_size = max((lvl.size for lvl in asks + bids), default=0.0)

        # Selectable rows in display order: asks top-to-bottom (best ask nearest
        # the mid), then bids best-first. The mid divider is not a cursor stop.
        self._levels = [("ask", lvl) for lvl in reversed(asks)] + [("bid", lvl) for lvl in bids]
        if self._cursor >= len(self._levels):
            self._cursor = max(0, len(self._levels) - 1)
        focused = self.has_focus

        out = Text()
        out.append(f"{'':>{bar_w}} {'price':>7} {'shares':>10}\n", style="bold dim")

        row = 0
        for level in reversed(asks):
            cursor = focused and row == self._cursor
            out.append_text(self._level_line(level, max_size, DOWN, ASK_BAR, bar_w, cursor))
            row += 1

        if book.midpoint is not None:
            out.append(
                f"---- mid {fmt.cents(book.midpoint)}  spread {fmt.cents(book.spread)} ----\n",
                style=f"bold {AMBER}",
            )
        elif not asks and not bids:
            out.append("empty book\n", style="dim")

        for level in bids:
            cursor = focused and row == self._cursor
            out.append_text(self._level_line(level, max_size, UP, BID_BAR, bar_w, cursor))
            row += 1

        self.update(out)
