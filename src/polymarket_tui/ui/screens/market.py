"""Market detail: live-polling order book + price history chart.

Logic lives in MarketPane (a widget) so NavHost can host it as the 70% child
of the drill split. This is the money path - MarketPane owns the live book
(`_book`) and the position strip; OrderPanel resolves it via the
`is_market_pane` marker (see order_panel._market_pane) rather than self.screen.
"""

from __future__ import annotations

import contextlib
import time
from decimal import Decimal

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.api.ws import MarketChannel
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market, OrderBook
from polymarket_tui.ui.theme import AMBER, DOWN, UP
from polymarket_tui.ui.tiers import ColumnSpec, Tier, TierAware, effective_tier, fit_columns
from polymarket_tui.ui.widgets.activity_panel import ActivityPanel
from polymarket_tui.ui.widgets.book_panel import BookPanel
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.order_details import cancel_confirm_text
from polymarket_tui.ui.widgets.order_panel import OrderPanel
from polymarket_tui.ui.widgets.price_chart import PriceChartPanel
from polymarket_tui.ui.widgets.trader_overview import TraderOverview
from polymarket_tui.ui.widgets.trades_table import TradesTable
from polymarket_tui.ui.widgets.vim_table import VimDataTable

BOOK_POLL_SECONDS = 3.0

# (key, label, width) per width tier. Compact (30% parent slot) keeps only
# outcome + price + 24h; the book, chart, and rails are hidden by CSS there.
OUTCOMES_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("outcome", "Outcome", 24),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("bid", "Bid", 7),
        ("ask", "Ask", 7),
        ("spread", "Spread", 7),
        ("vol", "Vol 24h", 9),
    ),
    "medium": (
        ("outcome", "Outcome", 24),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("bid", "Bid", 7),
        ("ask", "Ask", 7),
        ("spread", "Spread", 7),
        ("vol", "Vol 24h", 9),
    ),
    "compact": (
        ("outcome", "Outcome", 14),
        ("price", "Price", 7),
        ("change", "24h", 7),
    ),
}


class OutcomesTable(VimDataTable):
    """The market's outcome selector.

    right no longer opens an order - space does that now (consistent with the
    book, where space also starts an order). Like down past the last row, right
    flows into the order book below.
    """

    BINDINGS = [Binding("right", "into_book", "book", show=False)]

    def action_into_book(self) -> None:
        self.post_message(self.BottomReached(self))


class MarketPane(TierAware, Vertical):
    """Market detail body - hosted as a drill pane by NavHost.

    Owns the live order book in `_book`; OrderPanel finds this pane via the
    `is_market_pane` marker to read the book and refresh positions.
    """

    header_title = "market"
    is_market_pane = True  # marker for OrderPanel._market_pane() (no import cycle)

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "order('BUY')", "buy"),
        Binding("y", "select_outcome(0)", "yes", show=False),
        Binding("n", "select_outcome(1)", "no", show=False),
        Binding("enter", "enter_key", "buy", priority=False),
        Binding("b", "order('BUY')", "buy", show=False),
        Binding("s", "order('SELL')", "sell"),
        Binding("a", "toggle_trades", "trades"),
        Binding("i", "toggle_rules", "rules"),
        Binding("c", "toggle_activity('comments')", "comments", show=False),
        Binding("tab", "cycle_interval(1)", "timeframe"),
        Binding("shift+tab", "cycle_interval(-1)", "prev timeframe", show=False),
        Binding("R", "related", "related", show=False, key_display="R"),
        Binding("O", "open_web", "web", show=False, key_display="O"),
        Binding("e", "open_event", "event", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(
        self,
        market: Market,
        event: Event | None = None,
        order_side: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._market = market
        self._event = event
        self._outcome_index = 0  # 0 = YES/first outcome, 1 = NO
        self._interval = "ALL"  # full history first; tab/shift+tab narrows
        self._history: list = []
        self._book = None
        self._trades_expanded = False
        self._rules_visible = False
        self._pending_order_side = order_side  # open the order panel once the book arrives
        self._my_positions: list = []  # your holdings here (load_position)
        self._channel: MarketChannel | None = None  # live book over websockets (issue #1)
        self._columns_spec: list[ColumnSpec] = list(OUTCOMES_TIER_COLUMNS["full"])
        self.drill_key = ("market", market.slug)
        # True while a tier rebuild is restoring the cursor; row-highlight
        # events are ignored until the cursor lands on _outcome_index so the
        # rebuild can't flip the selected outcome (and reload book/history).
        self._syncing_cursor = False
        # Cancel from the market page: x on a book level arms this, y confirms.
        self._pending_cancel: list | None = None
        self._cancel_armed_at = 0.0

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title", id="market-title")
        with Horizontal(id="market-body"):
            # Book in the hero column (actionable prices first), trades in the
            # rail (live context) - swapped 2026-07-05 on Byron's request.
            with Vertical(id="market-left"):
                yield OutcomesTable(cursor_type="row", zebra_stripes=True, id="outcomes-table")
                yield Static(id="position-line")
                yield Static(id="orders-note")
                yield Static(id="market-cancel-strip")
                with Vertical(id="book-pane"):
                    yield Static(self._book_header(), id="book-title")
                    scroll = VerticalScroll(BookPanel(id="book"), id="book-scroll")
                    scroll.can_focus = False
                    yield scroll
                    yield OrderPanel(id="order-panel")
            with Vertical(id="trades-rail"):
                yield Static(" TRADES (a expands)", classes="screen-title", id="trades-title")
                yield TradesTable(compact=True, id="trades-table")
            with Vertical(id="rules-rail"):
                yield Static(" RULES", classes="screen-title")
                rules = VerticalScroll(
                    Static(self._rules_text(), id="rules-text"), id="rules-scroll"
                )
                rules.can_focus = False
                yield rules
            overview = VerticalScroll(
                TraderOverview(id="market-trader-overview"), id="market-overview-pane"
            )
            overview.can_focus = False
            yield overview
        with Vertical(id="market-chart-strip"):
            tabs = Tabs(*(Tab(k, id=f"iv-{k}") for k in INTERVALS), id="interval-tabs")
            tabs.can_focus = False
            yield tabs
            yield PriceChartPanel(id="price-chart")
            yield ActivityPanel(id="comments-panel")
        yield Static(self._info_line(), id="market-info", classes="subtle")

    def focus_inner(self) -> None:
        self.query_one("#outcomes-table", VimDataTable).focus()

    @property
    def current_book(self) -> OrderBook | None:
        return self._book

    # -- labels ------------------------------------------------------------

    def _outcome_label(self) -> str:
        outcomes = self._market.outcomes or ["Yes", "No"]
        try:
            return outcomes[self._outcome_index]
        except IndexError:
            return "?"

    def _title_line(self) -> str:
        m = self._market
        bits = [m.question.strip()]
        if m.end_date:
            when = fmt.end_date(m.end_date)
            bits.append(when if when == "ended" else f"ends {when}")
        if self._event and self._event.title.strip() != m.question.strip():
            bits.append(self._event.title.strip())  # one-line Static crops at the edge
        return "  |  ".join(bits)

    def _build_outcome_columns(self) -> None:
        table = self.query_one("#outcomes-table", VimDataTable)
        table.clear(columns=True)
        for key, label, width in self._columns_spec:
            table.add_column(label, width=width, key=key)

    def on_tier_changed(self, tier: Tier) -> None:
        self._apply_visibility()
        self._schedule_refit()

    def _schedule_refit(self) -> None:
        # Measure after layout settles: the slot tier is a cap, the column
        # set follows the outcome table's real width.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        self._refit_trades()
        table = self.query_one("#outcomes-table", VimDataTable)
        width = table.size.width
        if width <= 0 or not table.columns:
            return
        tier = effective_tier(self.tier, width, OUTCOMES_TIER_COLUMNS)
        spec = fit_columns(OUTCOMES_TIER_COLUMNS[tier], width, "outcome")
        if spec == self._columns_spec:
            return
        self._columns_spec = spec
        self._syncing_cursor = True
        self._build_outcome_columns()
        self._fill_outcomes()
        table.move_cursor(row=self._outcome_index)

    def _refit_trades(self) -> None:
        """Slim trade columns when the inline rail can't fit the full set."""
        trades = self.query_one(TradesTable)
        width = trades.size.width
        if width <= 0:
            return
        want_compact = not self._trades_expanded and width < 64
        if trades.compact != want_compact:
            trades.compact = want_compact
            trades.build_columns()
            self.load_trades()

    def _apply_visibility(self) -> None:
        """Panel visibility as one function of tier + trades state.

        Inline display flags override stylesheet rules, so tier CSS can't be
        trusted for panels this pane also toggles - own them all here.
        Compact suspends the expanded-trades view (outcomes only) without
        dropping _trades_expanded; it comes back at medium/full.
        """
        if not self.query("#market-left"):
            return  # not composed yet (early resize)
        compact = self.tier == "compact"
        expanded = self._trades_expanded and not compact
        self.query_one("#market-left").display = not expanded
        self.query_one("#book-pane").display = not compact and not expanded
        self.query_one("#market-overview-pane").display = expanded
        self.query_one("#rules-rail").display = (
            not compact
            and not expanded
            and (self._rules_visible or self.size.width >= 170)
        )
        rail = self.query_one("#trades-rail")
        rail.set_class(expanded, "expanded")
        rail.display = expanded or not compact
        self.query_one("#market-chart-strip").display = not compact
        self.query_one("#market-info").display = not compact

    def _fill_outcomes(self) -> None:
        """Outcome rows exactly like the event page; the cursor is the selector."""
        m = self._market
        table = self.query_one("#outcomes-table", VimDataTable)
        table.clear()
        columns = self._columns_spec
        yes = m.yes_price
        change = m.one_day_price_change
        for idx, label in enumerate((m.outcomes or ["Yes", "No"])[:2]):
            price = yes if idx == 0 else (None if yes is None else 1 - yes)
            bid = m.best_bid if idx == 0 else (None if m.best_ask is None else 1 - m.best_ask)
            ask = m.best_ask if idx == 0 else (None if m.best_bid is None else 1 - m.best_bid)
            delta = change if idx == 0 else (None if change is None else -change)
            cells = {
                "outcome": Text(label, style=f"bold {UP}" if idx == 0 else f"bold {DOWN}"),
                "price": Text(fmt.cents(price), style="bold"),
                "change": change_text(delta),
                "bid": Text(fmt.cents(bid), style=UP),
                "ask": Text(fmt.cents(ask), style=DOWN),
                "spread": fmt.cents(m.spread),
                "vol": fmt.vol(m.volume_24hr),
            }
            table.add_row(*(cells[key] for key, _, _ in columns), key=str(idx))

    def on_data_table_row_highlighted(self, event) -> None:
        if event.data_table.id == "trades-table":
            if self._trades_expanded:
                self._refresh_trade_overview()
            return
        if event.data_table.id != "outcomes-table" or event.cursor_row is None:
            return
        if self._syncing_cursor:
            if event.cursor_row == self._outcome_index:
                self._syncing_cursor = False
            return
        self._apply_outcome(event.cursor_row)

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "outcomes-table":
            self.action_order("BUY")
        elif event.data_table.id == "trades-table":
            trader = self.query_one(TradesTable).trader_at_cursor()
            if trader is not None:
                self.app.open_user(*trader)

    def _apply_outcome(self, index: int) -> None:
        if index == self._outcome_index:
            return
        # A resting order armed on the old outcome's book no longer applies.
        self._clear_pending_cancel()
        self._outcome_index = index
        self._book = None  # stale: belongs to the other outcome until load_book returns
        self.query_one(OrderPanel).set_outcome(self._outcome_index)
        self.query_one("#book-title", Static).update(self._book_header())
        # We subscribe to both tokens, so the flipped outcome's live book is
        # usually already available - render it instantly instead of "loading".
        live = self._channel.book(self._token_id) if self._channel else None
        if live is not None:
            self._book = live
            self.query_one(BookPanel).update_book(live)
        else:
            self.query_one(BookPanel).update("loading book...")
        self.load_book()
        self.load_history()
        self.load_own_orders()

    def on_vim_data_table_bottom_reached(self, message) -> None:
        # Down past the last outcome flows into the order book (cursor through
        # the levels); the chart no longer captures focus on the market page.
        if message.table.id == "outcomes-table":
            self._focus_book()

    def _focus_book(self) -> None:
        book = self.query_one(BookPanel)
        if self.tier == "compact" or not book.has_levels:
            return
        book.focus_top()
        book.focus()

    def _book_header(self) -> Text:
        """Book title with a feed badge: streaming when the socket is healthy,
        else a stale/polling note so the user knows the book is REST-refreshed.
        The word LIVE is reserved for the execution mode - a green LIVE next
        to the book read as real-money trading (journey review, 2026-07-05).
        Returned as Text (not markup) so the badge can't be parsed as a tag."""
        head = Text(
            f"ORDER BOOK - {self._outcome_label().upper()}"
            "  (down to browse - space: order  x: cancel)"
        )
        if self._channel is not None:
            badge = {
                "live": ("  streaming", UP),
                "stale": ("  STALE (polling)", AMBER),
                "down": ("  polling", "dim"),
            }.get(self._channel.status())
            if badge:
                head.append(badge[0], style=badge[1])
        return head

    def _rules_text(self) -> Text:
        desc = (self._market.description or "").strip()
        if not desc and self._event is not None:
            desc = (self._event.description or "").strip()
        if not desc:
            return Text("no rules provided", style="dim")
        return Text(desc, style="dim")

    def _info_line(self) -> str:
        m = self._market
        bits = []
        if m.volume_24hr is not None:
            bits.append(f"vol24h {fmt.vol(m.volume_24hr)}")
        if m.liquidity is not None:
            bits.append(f"liquidity {fmt.vol(m.liquidity)}")
        if m.order_price_min_tick_size:
            bits.append(f"tick {m.order_price_min_tick_size}")
        if m.order_min_size:
            bits.append(f"min size {m.order_min_size:.0f}")
        bits.append(f"book: live ws (fallback {BOOK_POLL_SECONDS:.0f}s REST)")
        return "  |  ".join(bits)

    # -- lifecycle ----------------------------------------------------------

    def on_resize(self) -> None:
        self._apply_visibility()
        if self._tier_ready:
            self._schedule_refit()

    def on_mount(self) -> None:
        self.query_one("#market-cancel-strip", Static).display = False
        self.query_one("#interval-tabs", Tabs).active = f"iv-{self._interval}"
        table = self.query_one("#outcomes-table", VimDataTable)
        self._columns_spec = list(OUTCOMES_TIER_COLUMNS[self.tier])
        self._build_outcome_columns()
        self._fill_outcomes()
        self._apply_visibility()
        table.focus()
        self.tier_ready()
        self._schedule_refit()
        self.query_one(ActivityPanel).configure(self._market, self._event)
        self.load_trades()
        self.set_interval(5.0, self.load_trades)
        self.load_book()
        self.load_history()
        self.load_position()
        self.load_own_orders()
        self.set_interval(BOOK_POLL_SECONDS, self.load_book)
        self.set_interval(10.0, self.load_own_orders)
        self._start_channel()
        # Refresh the live/stale/polling badge even when no frames arrive.
        self.set_interval(2.0, self._refresh_book_badge)

    def _start_channel(self) -> None:
        tokens = [t for t in self._market.clob_token_ids if t]
        if not tokens:
            return
        self._channel = MarketChannel(tokens, self._on_ws_update)
        self._channel.start()

    async def on_unmount(self) -> None:
        if self._channel is not None:
            await self._channel.stop()

    def _on_ws_update(self, kind: str, asset_id: str) -> None:
        """Called on the event loop when a market frame is applied."""
        if self._channel is None or asset_id != self._token_id:
            return
        if kind in ("book", "price_change"):
            book = self._channel.book(asset_id)
            if book is not None:
                self._book = book
                self.query_one(BookPanel).update_book(book)
                self._refresh_book_badge()
                self._refresh_outcome_prices(asset_id, book)

    def _refresh_book_badge(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#book-title", Static).update(self._book_header())

    def _refresh_outcome_prices(self, asset_id: str, book: OrderBook) -> None:
        """Keep the outcome table's bid/ask in step with the live book."""
        if self._token_id != asset_id:
            return
        table = self.query_one("#outcomes-table", VimDataTable)
        bb = book.best_bid.price if book.best_bid else None
        ba = book.best_ask.price if book.best_ask else None
        with contextlib.suppress(Exception):
            if bb is not None:
                table.update_cell(str(self._outcome_index), "bid", fmt.cents(bb))
            if ba is not None:
                table.update_cell(str(self._outcome_index), "ask", fmt.cents(ba))

    @work(exclusive=True, group="position")
    async def load_position(self) -> None:
        """Your holdings in this market, shown under the outcome table."""
        line = self.query_one("#position-line", Static)
        app = self.app
        if not app.settings.can_read_portfolio:
            line.update(Text(""))
            return
        try:
            positions = await app.portfolio.positions()
        except Exception:
            return
        tokens = set(self._market.clob_token_ids)
        mine = [p for p in positions if p.asset in tokens and p.size >= 0.01]
        self._my_positions = mine
        if not mine:
            line.update(Text(" no position in this market", style="dim"))
            return
        out = Text()
        out.append(" YOUR POSITION  ", style="bold")
        for i, p in enumerate(mine):
            if i:
                out.append("   |   ")
            out.append(f"{p.size:,.0f} ", style="bold")
            out.append(
                f"{p.outcome} ",
                style=f"bold {UP}" if p.outcome.lower() == "yes" else f"bold {DOWN}",
            )
            out.append(f"@ {fmt.cents(p.avg_price)} ", style="dim")
            out.append(f"now {fmt.cents(p.cur_price)}  ")
            pnl_style = UP if p.cash_pnl > 0 else DOWN if p.cash_pnl < 0 else "dim"
            out.append(f"{p.cash_pnl:+,.2f} ({p.percent_pnl:+.0f}%)", style=pnl_style)
        line.update(out)

    @work(exclusive=True, group="own-orders")
    async def load_own_orders(self) -> None:
        """Star the book levels that hold one of your resting orders."""
        app = self.app
        if not app.settings.can_auth:
            return
        try:
            await app.portfolio.open_orders()
        except Exception:
            return
        token = self._token_id
        if token is None:
            return
        mine = app.portfolio.orders_for_assets({token})
        self.query_one(BookPanel).set_own_orders(mine)
        market_orders = app.portfolio.orders_for_assets(
            {t for t in self._market.clob_token_ids if t}
        )
        self._own_order_count = len(market_orders)
        self._refresh_position_orders_note()

    def _refresh_position_orders_note(self) -> None:
        count = getattr(self, "_own_order_count", 0)
        note = self.query_one("#orders-note", Static)
        if count:
            note.update(
                Text(
                    f" {count} resting order{'s' if count != 1 else ''}"
                    " - down into the book, x on a starred (*) level cancels",
                    style=AMBER,
                )
            )
        else:
            note.update(Text(""))

    @property
    def _token_id(self) -> str | None:
        return self._market.token_id(self._outcome_index)

    # -- data loaders --------------------------------------------------------

    @work(exclusive=True, group="book")
    async def load_book(self) -> None:
        token = self._token_id
        panel = self.query_one(BookPanel)
        if token is None:
            panel.show_error("no order book (missing token id)")
            return
        # When the websocket is live it owns the book; REST is the fallback that
        # keeps things fresh while the socket is down or stale (issue #1).
        if self._channel is not None and self._channel.status() == "live":
            self._refresh_book_badge()
            self._maybe_open_pending_order()
            return
        try:
            book = await self.app.clob.order_book(token)
        except Exception as exc:
            panel.show_error(f"book unavailable: {exc}")
            return
        self._book = book
        panel.update_book(book)
        self._refresh_book_badge()
        self._maybe_open_pending_order()

    def _maybe_open_pending_order(self) -> None:
        if self._pending_order_side is not None:
            side, self._pending_order_side = self._pending_order_side, None
            self.action_order(side)

    @work(exclusive=True, group="history")
    async def load_history(self) -> None:
        token = self._token_id
        if token is None:
            return
        try:
            self._history = await self.app.clob.prices_history(token, self._interval)
        except Exception as exc:
            self.notify(f"history unavailable: {exc}", severity="warning", timeout=4)
            self._history = []
        self._draw_chart()

    # -- chart ----------------------------------------------------------------

    def _draw_chart(self) -> None:
        panel = self.query_one(PriceChartPanel)
        panel.show([(self._outcome_label(), self._history)], self._interval)

    # -- actions ----------------------------------------------------------------

    def action_select_outcome(self, index: int) -> None:
        # A y/n leaking through while the order panel is up (the confirming
        # state keeps focus on the panel, whose bindings no longer shadow
        # them) must not flip the outcome under the order.
        if self.query_one(OrderPanel).is_open:
            return
        self.query_one("#outcomes-table", VimDataTable).move_cursor(row=index)

    def action_set_interval_key(self, key: str) -> None:
        self._interval = key
        tabs = self.query_one("#interval-tabs", Tabs)
        tabs.active = f"iv-{key}"
        self.load_history()

    def action_cycle_interval(self, delta: int) -> None:
        keys = list(INTERVALS)
        idx = (keys.index(self._interval) + delta) % len(keys)
        self.action_set_interval_key(keys[idx])

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs.id == "interval-tabs" and event.tab.id:
            key = event.tab.id.removeprefix("iv-")
            if key != self._interval:
                self._interval = key
                self.load_history()

    def action_refresh(self) -> None:
        self.load_book()
        self.load_history()

    # -- order book navigation & cancel -----------------------------------------

    def on_book_panel_focus_above(self, message) -> None:
        """up-at-top / left in the book returns to the outcome table."""
        self._clear_pending_cancel()
        self.query_one("#outcomes-table", VimDataTable).focus()

    def on_book_panel_cursor_moved(self, message) -> None:
        # Retargeting the cursor invalidates any armed cancel from another level.
        self._clear_pending_cancel()

    def on_book_panel_row_actioned(self, message) -> None:
        """space on a book level: open the order panel prefilled from it."""
        self._clear_pending_cancel()
        app = self.app
        if not app.settings.can_auth:
            app.notify(
                "Trading needs a private key + funder - press A to authenticate",
                severity="warning",
            )
            return
        from polymarket_tui.services.orders import Side

        self.query_one(OrderPanel).open(
            self._market,
            Side(message.side),
            self._outcome_index,
            self._book,
            preset_price=Decimal(str(message.price)),
            preset_size=Decimal(str(message.size)),
        )

    def on_book_panel_cancel_requested(self, message) -> None:
        """x on a book level: arm a full-detail cancel confirm for order(s) there."""
        orders = message.orders
        if not orders:
            self.notify("No resting order of yours at that level", severity="warning", timeout=3)
            return
        self._pending_cancel = orders
        self._cancel_armed_at = time.monotonic() + 0.35
        strip = self.query_one("#market-cancel-strip", Static)
        strip.update(cancel_confirm_text(orders))
        strip.display = True

    def _clear_pending_cancel(self) -> None:
        if self._pending_cancel is not None:
            self._pending_cancel = None
            with contextlib.suppress(Exception):
                self.query_one("#market-cancel-strip", Static).display = False

    def action_enter_key(self) -> None:
        """enter confirms an armed cancel; otherwise it opens the buy panel."""
        if self._pending_cancel is not None:
            if time.monotonic() < self._cancel_armed_at:
                return  # queued enter - not a decision
            orders = self._pending_cancel
            self._clear_pending_cancel()
            for order in orders:
                self._start_cancel(order.id)
            return
        self.action_order("BUY")

    def _start_cancel(self, order_id: str) -> None:
        # App-lifetime worker: navigating off the pane must not drop an in-flight
        # cancel's result (mirrors the placement path in order_panel).
        app = self.app
        pane = self

        async def _cancel_and_report() -> None:
            result = await app.orders.cancel(order_id)
            if result.ok and result.dry_run:
                app.notify(
                    "DRY RUN: cancel not posted (set POLYMARKET_EXECUTION_LIVE=1)", timeout=6
                )
            elif result.ok:
                app.notify("Order cancelled")
                app.portfolio.invalidate()
                app.refresh_account_status()
            else:
                app.notify(f"Cancel failed: {result.error}", severity="error", timeout=8)
            if pane.is_mounted:
                pane.load_own_orders()
                pane.load_position()

        app.run_worker(_cancel_and_report(), group="cancel-order", exclusive=False)

    @work(exclusive=True, group="trades")
    async def load_trades(self) -> None:
        if not self._market.condition_id:
            return
        try:
            limit = 60 if self._trades_expanded else 30
            trades = await self.app.data.market_trades(self._market.condition_id, limit=limit)
        except Exception:
            return
        self.query_one(TradesTable).set_trades(trades)

    def action_toggle_rules(self) -> None:
        self._rules_visible = not self._rules_visible
        self._apply_visibility()
        self._schedule_refit()

    def action_toggle_trades(self) -> None:
        self._set_trades_expanded(not self._trades_expanded)

    def _set_trades_expanded(self, expanded: bool) -> None:
        self._trades_expanded = expanded
        self._apply_visibility()
        table = self.query_one(TradesTable)
        title = (
            " TRADES - right/enter opens trader, left collapses"
            if expanded
            else " TRADES (a expands)"
        )
        self.query_one("#trades-title", Static).update(title)
        self.load_trades()
        if expanded:
            table.focus()
            self._refresh_trade_overview()
        else:
            self.query_one("#outcomes-table", VimDataTable).focus()

    def _refresh_trade_overview(self) -> None:
        trader = self.query_one(TradesTable).trader_at_cursor()
        if trader is not None:
            self.query_one(TraderOverview).show_trader(*trader)

    def handle_back(self) -> bool:
        """left/escape step out one level before leaving the pane."""
        if self._pending_cancel is not None:
            self._clear_pending_cancel()
            return True
        panel = self.query_one(OrderPanel)
        if panel.is_open:
            panel.close()
            return True
        # In the order book, esc steps back to the outcome table before the pane.
        if self.query_one(BookPanel).has_focus:
            self.query_one("#outcomes-table", VimDataTable).focus()
            return True
        # At compact the trades view is suspended (not visible), so esc
        # should step out of the pane, not invisibly collapse it.
        if self._trades_expanded and self.tier != "compact":
            self._set_trades_expanded(False)
            return True
        return False

    def action_toggle_activity(self, mode: str) -> None:
        """c toggles comments into the chart strip; chart hides while shown."""
        panel = self.query_one(ActivityPanel)
        panel.toggle(mode)
        showing = panel.mode is not None
        self.query_one("#interval-tabs", Tabs).display = not showing
        self.query_one(PriceChartPanel).display = not showing

    def action_open_event(self) -> None:
        if self._event is not None:
            self.app.open_event(self._event)
            return
        self._fetch_and_open_event()

    @work(exclusive=True, group="open-event")
    async def _fetch_and_open_event(self) -> None:
        slug = self._market.event_slug
        event = None
        if slug:
            try:
                event = await self.app.gamma.event_by_slug(slug)
            except Exception:
                event = None
        if event is None:
            # Markets opened from positions carry no embedded event - refetch.
            try:
                fresh = await self.app.gamma.market_by_slug(self._market.slug)
                if fresh is not None and fresh.event_slug:
                    event = await self.app.gamma.event_by_slug(fresh.event_slug)
            except Exception:
                event = None
        if event is None:
            self.notify("No event found for this market", severity="warning")
            return
        self._event = event
        self.app.open_event(event)

    def action_related(self) -> None:
        if self._event is None:
            self.notify("No event context for this market", severity="warning")
            return
        self.app.open_related(self._event)

    def action_open_web(self) -> None:
        import webbrowser

        event_slug = self._market.event_slug or (self._event.slug if self._event else None)
        if event_slug:
            url = f"https://polymarket.com/event/{event_slug}/{self._market.slug}"
        else:
            # polymarket.com redirects /market/<slug> to the event page.
            url = f"https://polymarket.com/market/{self._market.slug}"
        webbrowser.open(url)
        self.notify(f"Opened {url}", timeout=3)

    def action_order(self, side: str) -> None:
        app = self.app
        if not app.settings.can_auth:
            app.notify(
                "Trading needs a private key + funder - press A to authenticate",
                severity="warning",
            )
            return
        from polymarket_tui.services.orders import Side

        panel = self.query_one(OrderPanel)
        if panel.is_open:
            panel.set_side(Side(side))
            return
        if Side(side) is Side.SELL:
            # Selling means selling shares you hold: if the cursor sits on an
            # outcome you don't own but you do own the other one, retarget
            # there first (the book reload then reopens the panel pending).
            owned = self._owned_outcome_index()
            if owned is not None and owned != self._outcome_index:
                outcomes = self._market.outcomes or ["Yes", "No"]
                self._pending_order_side = side
                self.action_select_outcome(owned)
                self.notify(f"Selling your {outcomes[owned]} position", timeout=3)
                return
        panel.open(self._market, Side(side), self._outcome_index, self._book)

    def _owned_outcome_index(self) -> int | None:
        """Index of the outcome you hold (largest position wins a rare tie)."""
        tokens = list(self._market.clob_token_ids)
        held = [
            (p.size, tokens.index(p.asset))
            for p in self._my_positions
            if p.asset in tokens
        ]
        if not held:
            return None
        return max(held)[1]

    def action_toggle_watch(self) -> None:
        slug = self._event.slug if self._event else self._market.slug
        watched = self.app.watchlist.toggle(slug)
        self.notify("Watching" if watched else "Unwatched", timeout=2)
