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

import contextlib
import math

from rich.text import Text
from textual.binding import Binding
from textual.geometry import Region
from textual.message import Message
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import BookLevel, OrderBook
from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.services.orders import decimals_for_tick
from polymarket_tui.ui.theme import AMBER, DOWN, UP

DEPTH = 10
# Browsing deeper than the default window: when the cursor comes within
# EXPAND_MARGIN rows of the deepest visible level on a side, that side reveals
# EXPAND_CHUNK more. Rows are only ever added at the extremes - never shifted
# or removed under the cursor (space arms an order from the row it sits on).
EXPAND_MARGIN = 3
EXPAND_CHUNK = 10
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
        Binding("m", "center", "mid", show=True),
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
        # Visible depth per side; grows as the cursor nears an edge (see
        # EXPAND_MARGIN). Reset per outcome, never per WS frame.
        self._ask_depth = DEPTH
        self._bid_depth = DEPTH
        self._more_asks_line = False  # "· n more" above the asks (scroll math)
        # The first book render (per outcome) drops the cursor at the mid -
        # the touch is what a trader acts on, not the deepest visible ask.
        self._cursor_centered = False
        # Has the user actually put the cursor on a level, or is it just parked
        # where the first render left it? The book takes focus by default when
        # the market pane opens, so "the book has focus" alone never meant the
        # user picked a price - and the parked row is the best ASK, which
        # silently overrode the SELL cash-out prefill with a price that cannot
        # cross. Only a deliberate move counts (see cursor_chosen).
        self._cursor_moved = False
        # Cents decimal places at the market's tick. Seeded from Gamma via
        # set_price_decimals, then taken from each book's own tick_size - the
        # exchange is the only authority on its current grid. 1 is the app-wide
        # default until either lands.
        self._price_decimals = 1
        # Whether the row cursor should draw. Tracked here, set synchronously in
        # on_focus/on_blur, rather than read from the has_focus reactive: on the
        # focus that on_focus itself handles, has_focus is not True yet, so the
        # first render into the book drew no cursor and the user had to press
        # down again to see it (landing on row 1).
        self._focused = False

    # -- state ------------------------------------------------------------------

    @property
    def has_levels(self) -> bool:
        return bool(self._levels)

    @property
    def cursor_price(self) -> float | None:
        """Price of the highlighted book level (None if the book has no levels).

        Lets the pane prefill an order from the price the cursor is sitting on
        when b/s/enter bubble up from the book (space already does this via
        RowActioned; these keys have no book binding so they reach MarketPane).
        """
        if not self._levels:
            return None
        return self._levels[self._cursor][1].price

    @property
    def cursor_chosen(self) -> bool:
        """True once the user moved the cursor onto a level themselves.

        Prefilling an order from `cursor_price` is only "the price you are
        looking at" if you put the cursor there. Until then it sits on the best
        ask, which is the wrong side of the book for a sell.
        """
        return self._cursor_moved

    def focus_top(self) -> None:
        """Enter the book at its top row (called when arrowing down into it)."""
        self._cursor = 0
        self._cursor_moved = True  # arrowing in is a deliberate landing

    def reset_depth(self) -> None:
        """Back to the default window (call when the shown token changes -
        an outcome flip must not inherit the other book's explored depth).
        The next render re-centers the cursor on the new book's mid."""
        self._cursor_moved = False  # a new book is nobody's chosen level yet
        self._ask_depth = DEPTH
        self._bid_depth = DEPTH
        self._cursor_centered = False

    def set_price_decimals(self, decimals: int) -> None:
        """Seed the tick resolution from Gamma before any book has arrived.

        Only a fallback: once a book lands, update_book takes the tick straight
        from the exchange (see _adopt_book_tick)."""
        if decimals != self._price_decimals:
            self._price_decimals = decimals
            if self._book is not None:
                self._render_book()

    def _adopt_book_tick(self, book: OrderBook) -> None:
        """Render at the tick the exchange stamped on this very book.

        The CLOB re-grids a market (0.01 -> 0.001) as its price nears 0 or 1.
        Reading the tick off each book means the panel follows that change with
        the frame that carries it, rather than showing 33c for a 33.4c level
        until the pane is reopened."""
        if book.tick_size:
            self._price_decimals = decimals_for_tick(book.tick_size)

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
        self._focused = True
        if self._book is not None:
            self._render_book()

    def on_blur(self) -> None:
        self._focused = False
        if self._book is not None:
            self._render_book()

    def show_error(self, message: str) -> None:
        self._book = None
        self._levels = []
        self.update(Text(message, style="dim"))

    def show_notice(self, content: Text) -> None:
        """Pane-supplied content in place of a book (closed-market resolution).
        Clears the levels so the cursor/cancel keys have nothing to act on."""
        self._book = None
        self._levels = []
        self.update(content)

    # -- actions ----------------------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        if not self._levels:
            if delta < 0:
                self.post_message(self.FocusAbove())
            return
        target = self._cursor + delta
        if target < 0:
            # Approached from below, row 0 is only reachable once every ask
            # is revealed (_maybe_expand shifts the cursor as rows prepend);
            # entering at the top row and pressing up steps out as always.
            self.post_message(self.FocusAbove())
            return
        if target >= len(self._levels):
            return  # clamp at the last row
        self._cursor = target
        self._cursor_moved = True
        self._maybe_expand(delta)
        self.post_message(self.CursorMoved())
        self._render_book()

    def _maybe_expand(self, delta: int) -> None:
        """Reveal more depth when the cursor nears the edge it is moving
        toward (up = deeper asks, down = deeper bids - approaching an edge
        while moving away from it must not grow that side).

        Asks render deepest-first, so deepening asks prepends rows - the
        cursor index shifts by the added count to stay on the same level."""
        book = self._book
        if book is None:
            return
        if delta < 0 and self._cursor < EXPAND_MARGIN and self._ask_depth < len(book.asks):
            shown = min(self._ask_depth, len(book.asks))
            self._ask_depth = min(self._ask_depth + EXPAND_CHUNK, len(book.asks))
            self._cursor += self._ask_depth - shown
        near_bottom = len(self._levels) - 1 - self._cursor < EXPAND_MARGIN
        if delta > 0 and near_bottom and self._bid_depth < len(book.bids):
            self._bid_depth = min(self._bid_depth + EXPAND_CHUNK, len(book.bids))

    def action_focus_above(self) -> None:
        self.post_message(self.FocusAbove())

    def _center_row(self) -> int:
        """Row hugging the mid: the best ask (the buy touch), or the best
        bid when the ask side is empty."""
        n_asks = sum(1 for kind, _ in self._levels if kind == "ask")
        return max(0, n_asks - 1)

    def action_center(self) -> None:
        """m: jump back to the mid after browsing depth."""
        if not self._levels:
            return
        self._cursor = self._center_row()
        self._cursor_moved = True  # pressing m is a choice, unlike the parked default
        self.post_message(self.CursorMoved())  # drop a stale armed cancel
        self._render_book()

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

    def _fmt_price(self, price: float) -> str:
        """A level price in cents at the market's tick resolution."""
        return f"{price * 100:.{self._price_decimals}f}c"

    def _fmt_mid(self, value: float | None) -> str:
        """Mid/spread in cents: tick resolution, plus one place when the mid
        lands on a half-tick (a 1c book with a 1c spread mids at x.5c)."""
        if value is None:
            return "-"
        c = value * 100
        decimals = self._price_decimals
        if abs(c - round(c, decimals)) > 1e-9:
            decimals += 1
        return f"{c:.{decimals}f}c"

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
        line.append(f" {self._fmt_price(level.price):>7}", style=style)
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
        self._adopt_book_tick(book)
        self._render_book()

    def _render_book(self) -> None:
        book = self._book
        if book is None:
            return
        bar_w = self._bar_width()
        asks = sorted(book.asks, key=lambda lvl: lvl.price)[: self._ask_depth]
        bids = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)[: self._bid_depth]
        hidden_asks = len(book.asks) - len(asks)
        hidden_bids = len(book.bids) - len(bids)
        self._more_asks_line = hidden_asks > 0
        max_size = max((lvl.size for lvl in asks + bids), default=0.0)

        # Selectable rows in display order: asks top-to-bottom (best ask nearest
        # the mid), then bids best-first. The mid divider is not a cursor stop.
        self._levels = [("ask", lvl) for lvl in reversed(asks)] + [("bid", lvl) for lvl in bids]
        if not self._cursor_centered and self._levels:
            # First render of this book: start at the mid, not the deepest ask.
            self._cursor_centered = True
            self._cursor = self._center_row()
        if self._cursor >= len(self._levels):
            self._cursor = max(0, len(self._levels) - 1)
        focused = self._focused

        out = Text()
        out.append(f"{'':>{bar_w}} {'price':>7} {'shares':>10}\n", style="bold dim")
        if hidden_asks:
            out.append(f"· {hidden_asks} more\n", style="dim")

        row = 0
        for level in reversed(asks):
            cursor = focused and row == self._cursor
            out.append_text(self._level_line(level, max_size, DOWN, ASK_BAR, bar_w, cursor))
            row += 1

        if book.midpoint is not None:
            out.append(
                f"---- mid {self._fmt_mid(book.midpoint)}"
                f"  spread {self._fmt_mid(book.spread)} ----\n",
                style=f"bold {AMBER}",
            )
        elif not asks and not bids:
            out.append("empty book\n", style="dim")

        for level in bids:
            cursor = focused and row == self._cursor
            out.append_text(self._level_line(level, max_size, UP, BID_BAR, bar_w, cursor))
            row += 1

        if hidden_bids:
            out.append(f"· {hidden_bids} more\n", style="dim")

        self.update(out)
        if focused:
            self._scroll_cursor_visible()

    def _scroll_cursor_visible(self) -> None:
        """Keep the cursor row in view when the book overflows its pane.

        The whole book is one Static, so Textual's focus-scrolling can't
        follow the in-widget cursor (only the widget is focused, the cursor is
        styled text). On a short terminal the pane clips to a few rows, so
        scroll the wrapping container to the cursor's line or the levels below
        the fold are unreachable. Line = header(1) + cursor, plus the mid
        divider once the cursor is in the bids.
        """
        parent = self.parent
        if parent is None or not getattr(parent, "is_scrollable", False):
            return
        n_asks = sum(1 for kind, _ in self._levels if kind == "ask")
        has_mid = self._book is not None and self._book.midpoint is not None
        line = (
            1  # header
            + (1 if self._more_asks_line else 0)
            + self._cursor
            + (1 if has_mid and self._cursor >= n_asks else 0)
        )
        # On an edge row, pull the adjacent "· n more" indicator into view too.
        height = 1
        if self._cursor == 0 and self._more_asks_line:
            line -= 1
            height = 2
        elif self._cursor == len(self._levels) - 1:
            height = 2  # covers the tail indicator when one is rendered
        with contextlib.suppress(Exception):
            parent.scroll_to_region(Region(0, line, 1, height), animate=False)
