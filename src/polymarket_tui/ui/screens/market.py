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

from rich import box
from rich.align import Align
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.api.ws import MarketChannel
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market, OrderBook
from polymarket_tui.services.orders import price_decimals
from polymarket_tui.ui.follow import CursorFollow
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.theme import AMBER, BLUE, DOWN, UP
from polymarket_tui.ui.tiers import Tier, TierAware
from polymarket_tui.ui.widgets.book_panel import BookPanel
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.order_details import cancel_confirm_text
from polymarket_tui.ui.widgets.order_panel import OrderPanel
from polymarket_tui.ui.widgets.price_chart import PriceChartPanel
from polymarket_tui.ui.widgets.trader_overview import TraderOverview
from polymarket_tui.ui.widgets.trades_table import TradesTable

BOOK_POLL_SECONDS = 3.0

CHIP_MIN_WIDTH = 18  # below two of these + the gap, the chips stack
CHIP_GAP = 2


class OutcomesToggle(Static):
    """The market's YES/NO selector, drawn as two side-by-side chips.

    A Polymarket market is always a single binary pair, so the old two-row
    DataTable (a header + grid to show two rows, half of them a mechanical
    complement of the other) was more chrome than the data earned. Here the
    focused chip IS the selected outcome; the order book below carries the
    live depth, so a chip only needs the price and 24h move.

    left/right flip sides (left off YES steps out, right off NO drops into
    the book); down also drops into the book; enter/space bubble up to the
    pane's order bindings. y/n jump straight to a side via `select`.
    """

    can_focus = True

    BINDINGS = [
        Binding("left", "prev", "prev", show=False),
        Binding("right", "next", "next", show=False),
        Binding("down", "into_book", "book", show=False),
    ]

    class OutcomeChanged(Message):
        """The selected side moved - flip the book/order panel/chart to it."""

        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class IntoBook(Message):
        """down, or right off the last chip: flow focus into the book below."""

    class StepOut(Message):
        """left off the first chip: step out one level (nav back)."""

    def __init__(self, market: Market, index: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._market = market
        self._index = index  # 0 = YES/first outcome, 1 = NO
        self._live_yes_mid: float | None = None  # live book mid overrides the snapshot

    # -- selection ----------------------------------------------------------

    def select(self, index: int) -> None:
        """Move the selection (y/n, cashout retarget). Emits only on a change."""
        index = 0 if index <= 0 else 1
        if index == self._index:
            return
        self._index = index
        self.refresh()
        self.post_message(self.OutcomeChanged(index))

    def action_prev(self) -> None:
        if self._index == 0:
            self.post_message(self.StepOut())
        else:
            self.select(0)

    def action_next(self) -> None:
        if self._index == 1:
            self.post_message(self.IntoBook())
        else:
            self.select(1)

    def action_into_book(self) -> None:
        self.post_message(self.IntoBook())

    # -- live prices --------------------------------------------------------

    def update_from_book(self, index: int, book: OrderBook) -> None:
        """Track the live book mid on the headline chips (best bid/ask avg).

        The book streams one token; the sibling outcome is its complement, so
        one book refreshes both chips. No-ops if it is not the shown side."""
        if index != self._index:
            return
        bid = book.best_bid.price if book.best_bid else None
        ask = book.best_ask.price if book.best_ask else None
        if bid is None or ask is None:
            return
        mid = (bid + ask) / 2
        yes_mid = mid if index == 0 else 1 - mid
        if yes_mid != self._live_yes_mid:
            self._live_yes_mid = yes_mid
            self.refresh()

    # -- rendering ----------------------------------------------------------

    def _chip(self, idx: int, width: int) -> Panel:
        m = self._market
        names = m.outcomes or ["Yes", "No"]
        label = names[idx] if idx < len(names) else ("Yes", "No")[idx]
        is_yes = idx == 0
        selected = idx == self._index
        base_yes = self._live_yes_mid if self._live_yes_mid is not None else m.yes_price
        price = base_yes if is_yes else (None if base_yes is None else 1 - base_yes)
        change = m.one_day_price_change
        delta = change if is_yes else (None if change is None else -change)
        color = UP if is_yes else DOWN
        body = Text()
        body.append(fmt.cents(price), style="bold")
        body.append("  ")
        body.append_text(change_text(delta))
        return Panel(
            Align.center(body),
            title=Text(label.upper(), style=f"bold {color}"),
            title_align="left",
            border_style=BLUE if selected else "dim",
            box=box.HEAVY if selected else box.ROUNDED,
            style="" if selected else "dim",
            width=width,
            height=3,
            padding=(0, 1),
        )

    def render(self) -> RenderableType:
        # The pair splits the measured width (the book below sets the column's
        # visual width - fixed chips left a ragged gap beside it); too narrow
        # for two minimum chips, they stack full-width instead.
        total = self.size.width or 80
        grid = Table.grid()
        if total < 2 * CHIP_MIN_WIDTH + CHIP_GAP:
            grid.add_column()
            grid.add_row(self._chip(0, total))
            grid.add_row(self._chip(1, total))
        else:
            half = (total - CHIP_GAP) // 2
            grid.add_column()
            grid.add_column(width=CHIP_GAP)  # gap
            grid.add_column()
            # Odd leftover column goes to the NO chip so the pair spans total.
            grid.add_row(self._chip(0, half), "", self._chip(1, total - CHIP_GAP - half))
        return grid

    def on_resize(self) -> None:
        self.refresh()  # side-by-side vs stacked follows the measured width


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
        Binding("enter", "enter_key", "buy", show=False, priority=False),
        Binding("b", "order('BUY')", "buy", show=False),
        Binding("s", "order('SELL')", "sell"),
        Binding("a", "toggle_trades", "trades"),
        Binding("i", "rules", "rules"),
        Binding("c", "comments", "comments", show=False),
        # tab cycles the screen's primary selector - here that is the
        # outcome pair (binary, so both directions flip). Timeframe, being
        # history, demotes to t.
        Binding("tab", "flip_outcome", "yes/no"),
        Binding("shift+tab", "flip_outcome", "flip outcome", show=False),
        Binding("t", "cycle_interval(1)", "timeframe"),
        Binding("r", "related", "related", show=False),
        Binding("O", "open_web", "web", show=False, key_display="O"),
        Binding("e", "open_event", "event", show=False),
    ]

    def __init__(
        self,
        market: Market,
        event: Event | None = None,
        order_side: str | None = None,
        order_size: Decimal | None = None,
        outcome_index: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._market = market
        self._event = event
        # 0 = YES/first outcome, 1 = NO; a portfolio cashout lands directly
        # on the outcome the position holds.
        self._outcome_index = outcome_index or 0
        self._interval = "ALL"  # full history first; tab/shift+tab narrows
        self._history: list = []
        self._book = None
        self._trades_expanded = False
        self._pending_order_side = order_side  # open the order panel once the book arrives
        self._pending_order_size = order_size  # prefill (cashout: the full position)
        self._my_positions: list = []  # your holdings here (load_position)
        self._channel: MarketChannel | None = None  # live book over websockets (issue #1)
        # Throttled cursor-follows: the ws-cached book renders instantly on an
        # outcome flip, but the REST refresh / history / own-orders fetches
        # and the trader overview only fire once the cursor settles.
        self._outcome_follow = CursorFollow(self, self._load_outcome_data, 0.2)
        self._trade_follow = CursorFollow(self, self._refresh_trade_overview, 0.2)
        self.drill_key = ("market", market.slug)
        # Cancel from the market page: x on a book level arms this, y confirms.
        self._pending_cancel: list | None = None
        self._cancel_armed_at = 0.0
        # A fill is settling: positions snapshot to compare backoff polls
        # against, and the pending poll timers (refresh_after_fill).
        self._fill_baseline: dict[str, float] | None = None
        self._fill_timers: list = []

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title", id="market-title")
        with Horizontal(id="market-body"):
            # Book in the hero column (actionable prices first), trades in the
            # rail (live context) - swapped 2026-07-05 on Byron's request.
            with Vertical(id="market-left"):
                yield OutcomesToggle(self._market, self._outcome_index, id="outcomes-toggle")
                yield Static(id="position-line")
                yield Static(id="orders-note")
                with Vertical(id="book-pane"):
                    yield Static(self._book_header(), id="book-title")
                    scroll = VerticalScroll(BookPanel(id="book"), id="book-scroll")
                    scroll.can_focus = False
                    yield scroll
            with Vertical(id="trades-rail"):
                # Both money actions share one place - the top of the right rail
                # (Byron, 2026-07-06). Placing opens the OrderPanel here; an x on
                # a book level arms the cancel confirm in the same slot. Only one
                # is ever active, and the book stays fully visible on the left in
                # both flows.
                yield OrderPanel(id="order-panel")
                yield Static(id="market-cancel-strip")
                yield Static(" TRADES (a expands)", classes="screen-title", id="trades-title")
                yield TradesTable(compact=True, id="trades-table")
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
        yield Static(self._info_line(), id="market-info", classes="subtle")

    def focus_inner(self) -> None:
        # The book is the default surface (actionable prices first, cursor
        # starting at the mid); at compact the book is hidden, so the
        # outcome chips take focus instead (hidden widgets swallow keys).
        if self.tier == "compact":
            self.query_one(OutcomesToggle).focus()
        else:
            self.query_one(BookPanel).focus()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Only advertise (and honor) keys whose effect is visible right now.

        At compact every panel except the outcome list is hidden, so the
        order/trades/chart keys would act on invisible widgets - space used
        to open the order panel with focus in a hidden price field. Comments
        and rules are pop-outs (overlays over the whole pane), so they stay
        available at every tier.
        """
        if self.tier == "compact" and action in (
            "order",
            "enter_key",
            "toggle_trades",
            "cycle_interval",
        ):
            return False
        if action == "toggle_trades" and self._order_panel_open():
            return False
        if action in ("order", "enter_key") and self._market.closed:
            return False  # nothing to place on a resolved market
        return True

    def _order_panel_open(self) -> bool:
        panel = self.query(OrderPanel)
        return bool(panel) and panel.first(OrderPanel).is_open

    @property
    def current_book(self) -> OrderBook | None:
        return self._book

    # -- labels ------------------------------------------------------------

    def _outcome_label(self, index: int | None = None) -> str:
        outcomes = self._market.outcomes or ["Yes", "No"]
        try:
            return outcomes[self._outcome_index if index is None else index]
        except IndexError:
            return "?"

    def _title_line(self) -> str:
        m = self._market
        bits = [m.question.strip()]
        status = fmt.market_status(m)
        if status:
            bits.append(status)
        if self._event and self._event.title.strip() != m.question.strip():
            bits.append(self._event.title.strip())  # .screen-title wraps: full name shows
        return "  |  ".join(bits)

    def on_tier_changed(self, tier: Tier) -> None:
        self._apply_visibility()
        self._schedule_refit()
        self.refresh_bindings()  # the footer gates on tier (check_action)

    def _schedule_refit(self) -> None:
        # The outcome selector reflows itself; only the inline trades rail
        # still needs a measured refit once the layout settles.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        if not alive(self):
            return  # call_after_refresh can fire after the pane is torn down
        self._refit_trades()

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
        elif trades.fit_trader_column():
            # Full set already shown; the expanded rail resized - regrow Trader.
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
        rail = self.query_one("#trades-rail")
        rail.set_class(expanded, "expanded")
        rail.display = expanded or not compact
        self.query_one("#market-chart-strip").display = not compact
        self.query_one("#market-info").display = not compact
        # The book holds default focus; if this pass just hid it (compact),
        # a hidden-but-focused widget would swallow every key.
        if compact and self.query_one(BookPanel).has_focus:
            self.query_one(OutcomesToggle).focus()

    def on_outcomes_toggle_outcome_changed(self, message: OutcomesToggle.OutcomeChanged) -> None:
        self._apply_outcome(message.index)

    def on_outcomes_toggle_into_book(self, message: OutcomesToggle.IntoBook) -> None:
        self._focus_book()

    def on_outcomes_toggle_step_out(self, message: OutcomesToggle.StepOut) -> None:
        self.app.action_nav_back()

    def on_data_table_row_highlighted(self, event) -> None:
        if event.data_table.id == "trades-table" and self._trades_expanded:
            self._trade_follow()  # show_trader fetches - never per key-repeat row

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "trades-table":
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
        # Depth explored on the old outcome's book does not carry over.
        self.query_one(BookPanel).reset_depth()
        self.query_one(OrderPanel).set_outcome(self._outcome_index)
        self.query_one("#book-title", Static).update(self._book_header())
        # We subscribe to both tokens, so the flipped outcome's live book is
        # usually already available - render it instantly instead of "loading".
        live = self._channel.book(self._token_id) if self._channel else None
        if self._market.closed:
            self._show_resolution()  # the flip must not clobber the summary
        elif live is not None:
            self._book = live
            self.query_one(BookPanel).update_book(live)
        else:
            self.query_one(BookPanel).update("loading book...")
        self._outcome_follow()

    def _load_outcome_data(self) -> None:
        """The fetch tail of an outcome flip - throttled behind _outcome_follow."""
        self.load_book()
        self.load_history()
        self.load_own_orders()

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
        if self._market.closed:
            # The slot carries the resolution summary; no book, no feed.
            return Text("RESOLUTION")
        head = Text(
            f"ORDER BOOK - {self._outcome_label().upper()}"
            "  (space: order  x: cancel  m: mid)"
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

    def _show_resolution(self) -> None:
        """Fill the book slot with the resolution: closed markets have an
        empty book, and the outcome is the one thing left worth reading."""
        m = self._market
        self.query_one("#book-title", Static).update(self._book_header())
        out = Text()
        winner = m.winning_outcome
        if winner is not None:
            side = m.outcomes.index(winner) if winner in m.outcomes else 0
            out.append(f"{winner} won", style=f"bold {UP if side == 0 else DOWN}")
        else:
            out.append("market closed", style="bold")
        when = fmt.date_abs(m.closed_time or m.end_date)
        if when:
            out.append(f"  {when}", style="dim")
        out.append("\n")
        status = m.uma_resolution_status
        if status and status != "resolved":
            # In-flight oracle states (proposed/disputed) - rare but loud.
            out.append(f"oracle status: {status}\n", style=AMBER)
        out.append("\nwinning shares redeem at 100c on polymarket.com", style="dim")
        out.append("\n(O opens this market on the web)", style="dim")
        self.query_one(BookPanel).show_notice(out)

    def _rules_body(self) -> str:
        """Raw resolution text for the rules pop-out - market first, then event."""
        desc = (self._market.description or "").strip()
        if not desc and self._event is not None:
            desc = (self._event.description or "").strip()
        return desc

    def _info_line(self) -> str:
        m = self._market
        bits = []
        if m.volume_24hr is not None:
            bits.append(f"vol24h {fmt.vol(m.volume_24hr)}")
        if m.spread is not None:
            bits.append(f"spread {fmt.cents(m.spread)}")
        if m.liquidity is not None:
            bits.append(f"liquidity {fmt.vol(m.liquidity)}")
        if m.order_price_min_tick_size:
            bits.append(f"tick {m.order_price_min_tick_size}")
        if m.order_min_size:
            bits.append(f"min size {m.order_min_size:.0f}")
        if m.closed:
            bits.append("market closed - trading disabled")
        else:
            bits.append(f"book: live ws (fallback {BOOK_POLL_SECONDS:.0f}s REST)")
        return "  |  ".join(bits)

    # -- lifecycle ----------------------------------------------------------

    def on_resize(self) -> None:
        self._apply_visibility()
        if self._tier_ready:
            self._schedule_refit()
        self.refresh_bindings()  # the i-rules gate follows the pane width

    def on_mount(self) -> None:
        self.query_one("#market-cancel-strip", Static).display = False
        self.query_one("#interval-tabs", Tabs).active = f"iv-{self._interval}"
        # Book prices render at this market's tick (no 33.0c on a 1c tick).
        self.query_one(BookPanel).set_price_decimals(price_decimals(self._market))
        # The toggle renders _outcome_index selected from birth (a cashout
        # opens straight onto the held side), so no cursor restore is needed.
        self._apply_visibility()
        self.focus_inner()
        self.tier_ready()
        self._schedule_refit()
        self.load_trades()
        self.set_interval(5.0, self.load_trades)
        self.load_history()
        self.load_position()
        if self._market.closed:
            # Resolved: the book is empty and nothing can rest on it - show
            # the resolution in its slot and skip the whole feed machinery.
            self._show_resolution()
        else:
            self.load_book()
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
        if not alive(self):
            return  # a frame can land in the teardown window (children pruned)
        if kind in ("book", "price_change"):
            book = self._channel.book(asset_id)
            if book is not None:
                self._book = book
                self.query_one(BookPanel).update_book(book)
                self._refresh_book_badge()
                with contextlib.suppress(Exception):
                    self.query_one(OutcomesToggle).update_from_book(self._outcome_index, book)

    def _refresh_book_badge(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#book-title", Static).update(self._book_header())

    @work(exclusive=True, group="position")
    async def load_position(self, force: bool = False) -> None:
        """Your holdings in this market, shown under the outcome table."""
        line = self.query_one("#position-line", Static)
        app = self.app
        if not app.settings.can_read_portfolio or app.settings.polymarket_hide_balances:
            line.update(Text(""))
            return
        try:
            positions = await app.portfolio.positions(force=force)
        except Exception:
            return
        if not alive(self):
            return  # pane torn down while we fetched
        tokens = set(self._market.clob_token_ids)
        mine = [p for p in positions if p.asset in tokens and p.size >= 0.01]
        self._my_positions = mine
        if self._fill_baseline is not None:
            # A fill is settling: once data-api reflects a changed position,
            # stop the backoff polls (refresh_after_fill).
            if {p.asset: p.size for p in mine} != self._fill_baseline:
                self._fill_baseline = None
                for timer in self._fill_timers:
                    timer.stop()
                self._fill_timers = []
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
    async def load_own_orders(self, force: bool = False) -> None:
        """Star the book levels that hold one of your resting orders."""
        if self._market.closed:
            return  # the exchange cancels resting orders when a market closes
        app = self.app
        if not app.settings.can_auth:
            return
        try:
            await app.portfolio.open_orders(force=force)
        except Exception:
            return
        if not alive(self):
            return  # pane torn down while we fetched
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

    # -- post-fill refresh ----------------------------------------------------

    # data-api indexes fills a few seconds late, so one immediate refetch
    # after a fill re-renders the stale holdings it just fetched. Positions
    # re-poll on this backoff until they actually move; open orders come
    # straight from the CLOB (no indexer), so one forced refetch suffices.
    FILL_POLL_DELAYS = (2.0, 5.0, 10.0, 20.0)

    def involves(self, asset_id: str, condition_id: str) -> bool:
        """Does a user order/fill event touch this pane's market?"""
        m = self._market
        return bool(asset_id and asset_id in m.clob_token_ids) or bool(
            condition_id and condition_id == m.condition_id
        )

    def refresh_after_fill(self) -> None:
        """An order of ours changed (ws event / a post landed): refresh the
        starred book levels now and poll positions with backoff until
        data-api catches up. No optimistic rendering - the position line
        only ever shows what the API returned (Byron, 2026-07-06)."""
        tokens = {t for t in self._market.clob_token_ids if t}
        self._fill_baseline = {
            p.asset: p.size for p in self._my_positions if p.asset in tokens
        }
        self.load_own_orders(force=True)
        self.load_position(force=True)
        for timer in self._fill_timers:
            timer.stop()
        self._fill_timers = [
            self.set_timer(delay, self._fill_poll) for delay in self.FILL_POLL_DELAYS
        ]

    def _fill_poll(self) -> None:
        if self._fill_baseline is None:
            return  # the changed position already landed - polls stopped
        self.load_position(force=True)

    # -- data loaders --------------------------------------------------------

    @work(exclusive=True, group="book")
    async def load_book(self) -> None:
        if self._market.closed:
            return  # the book slot shows the resolution (_show_resolution)
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
            if alive(self):
                panel.show_error(f"book unavailable: {exc}")
            return
        if not alive(self):
            return  # pane torn down while we fetched
        if self._channel is not None and self._channel.status() == "live":
            # The socket recovered while REST was in flight: its book is
            # newer - keep it rather than clobbering with the snapshot.
            self._refresh_book_badge()
            self._maybe_open_pending_order()
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
        # Closed market: relative windows anchor to the close, not to now
        # (now-relative queries return nothing once trading stops).
        end_ts: int | None = None
        if self._market.closed:
            anchor = self._market.closed_time or self._market.end_date
            if anchor is not None:
                end_ts = int(anchor.timestamp())
        try:
            self._history = await self.app.clob.prices_history(
                token, self._interval, end_ts=end_ts
            )
        except Exception as exc:
            self.notify(f"history unavailable: {exc}", severity="warning", timeout=4)
            self._history = []
        if not alive(self):
            return  # pane torn down while we fetched
        self._draw_chart()

    # -- chart ----------------------------------------------------------------

    def _draw_chart(self) -> None:
        panel = self.query_one(PriceChartPanel)
        panel.show([(self._outcome_label(), self._history)], self._interval)

    # -- actions ----------------------------------------------------------------

    def action_flip_outcome(self) -> None:
        """tab: flip YES/NO - the outcome pair is this screen's primary selector."""
        self.action_select_outcome(1 - self._outcome_index)

    def action_select_outcome(self, index: int) -> None:
        # A y/n leaking through while the order panel is up (the confirming
        # state keeps focus on the panel, whose bindings no longer shadow
        # them) must not flip the outcome under the order.
        if self.query_one(OrderPanel).is_open:
            return
        self.query_one(OutcomesToggle).select(index)

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
        """The global r: everything this pane shows, not just book+chart."""
        self.load_book()
        self.load_history()
        self.load_trades()
        self.load_position()
        self.load_own_orders()

    # -- order book navigation & cancel -----------------------------------------

    def on_book_panel_focus_above(self, message) -> None:
        """up-at-top / left in the book returns to the outcome table."""
        self._clear_pending_cancel()
        self.query_one(OutcomesToggle).focus()

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
        # Same arming beat as the order strip (ConfirmModal.ARM_DELAY_S): swallow
        # a queued enter, but stay below human reaction so the deliberate confirm
        # lands on the first press.
        self._cancel_armed_at = time.monotonic() + 0.15
        strip = self.query_one("#market-cancel-strip", Static)
        strip.border_title = "CANCEL ORDER"
        strip.update(cancel_confirm_text(orders, show_chip=False))
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
        if not alive(self):
            return  # pane torn down while we fetched
        self.query_one(TradesTable).set_trades(trades)

    def action_rules(self) -> None:
        """i opens the resolution rules in a reading pop-out."""
        self.app.open_rules(f"RULES - {self._market.question.strip()}", self._rules_body())

    def action_comments(self) -> None:
        """c opens the event's comment thread in a reading pop-out."""
        self.app.open_comments(self._event)

    def action_toggle_trades(self) -> None:
        self._set_trades_expanded(not self._trades_expanded)

    def _set_trades_expanded(self, expanded: bool) -> None:
        self._trades_expanded = expanded
        self._apply_visibility()
        table = self.query_one(TradesTable)
        # The expanded view is the trader view (right/enter opens the trader),
        # so it always carries the full column set - USDC and Trader. Widen
        # the columns now so the first load renders them; _schedule_refit
        # re-slims back to the compact rail on collapse (width-driven).
        if expanded and table.compact:
            table.compact = False
            table.build_columns()
        title = (
            " TRADES - right/enter opens trader, left collapses"
            if expanded
            else " TRADES (a expands)"
        )
        self.query_one("#trades-title", Static).update(title)
        self.load_trades()
        self._schedule_refit()
        if expanded:
            table.focus()
            self._refresh_trade_overview()
        else:
            self.focus_inner()

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
            self.query_one(OutcomesToggle).focus()
            return True
        # At compact the trades view is suspended (not visible), so esc
        # should step out of the pane, not invisibly collapse it.
        if self._trades_expanded and self.tier != "compact":
            self._set_trades_expanded(False)
            return True
        return False

    def action_open_event(self) -> None:
        if self._event is not None:
            self._go_to_event(self._event)
            return
        self._fetch_and_open_event()

    def _go_to_event(self, event: Event) -> None:
        """`e` steps up to the multi-outcome event view.

        A binary event has a single market, so this pane already is that view -
        open_event would route back to this same market and drill a duplicate
        level (breadcrumb repeats, a bare YES/NO chip pane lands in the 30%
        slot). Say so instead.

        For a real multi-outcome event, open it solo so it fills the window.
        When the event is already our parent in the trail (drilled down from
        it), open_event reuses that pane and this is a plain step back up; when
        it is not (reached from Portfolio/search/a position), solo stops the
        source market from lingering as a confusing YES/NO strip on the left."""
        if event.is_binary:
            self.notify("Single-market event - you're already viewing it", timeout=3)
            return
        self.app.open_event(event, solo=True)

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
        self._go_to_event(event)

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
        # Reached via RowSelected (enter) as well as the gated bindings: at
        # compact the order panel is hidden - never open an invisible form.
        if self.tier == "compact":
            return
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
                self._pending_order_side = side
                self.action_select_outcome(owned)
                self.notify(f"Selling your {self._outcome_label(owned)} position", timeout=3)
                return
        preset_price = preset_size = None
        if self._pending_order_size is not None:
            preset_size, self._pending_order_size = self._pending_order_size, None
        if Side(side) is Side.SELL:
            # Selling means getting out: prefill the full held size at the
            # live bid so the order can fill immediately (s -> enter -> enter
            # cashes out). Both fields stay editable - trim the size, bump
            # the price, or type '50%' over it; review + enter still confirm.
            if preset_size is None:
                held = next(
                    (p.size for p in self._my_positions if p.asset == self._token_id),
                    None,
                )
                if held is not None:
                    preset_size = Decimal(str(held))
            if self._book is not None and self._book.best_bid:
                preset_price = Decimal(str(self._book.best_bid.price))
        # b/s/enter while the order book has focus: prefill the highlighted
        # level's price - the user is acting on the price they are looking at,
        # not the mid/touch default (space in the book already does this via
        # RowActioned; those keys have no book binding, so they land here). Wins
        # over the SELL best-bid default; the held size prefill above stays.
        book = self.query_one(BookPanel)
        if book.has_focus and book.cursor_price is not None:
            preset_price = Decimal(str(book.cursor_price))
        panel.open(
            self._market,
            Side(side),
            self._outcome_index,
            self._book,
            preset_price=preset_price,
            preset_size=preset_size,
        )

    def _owned_outcome_index(self) -> int | None:
        """Index of the outcome you hold (largest position wins a rare tie).

        Falls back to the service's last-known positions: a fill event
        invalidates the cache mid-open, and s pressed while load_position
        refetches would otherwise silently target the wrong side (C7 flake).
        """
        tokens = list(self._market.clob_token_ids)
        held = [
            (p.size, tokens.index(p.asset))
            for p in self._my_positions
            if p.asset in tokens
        ]
        if not held:
            held = [
                (pos.size, idx)
                for idx, token in enumerate(tokens)
                if (pos := self.app.portfolio.position_for(token)) is not None
                and pos.size >= 0.01
            ]
        if not held:
            return None
        return max(held)[1]
