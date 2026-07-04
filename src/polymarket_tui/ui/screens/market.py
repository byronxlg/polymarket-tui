"""Market detail: live-polling order book + price history chart."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.widgets.activity_panel import ActivityPanel
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.book_panel import BookPanel
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.order_panel import OrderPanel
from polymarket_tui.ui.widgets.price_chart import PriceChartPanel
from polymarket_tui.ui.widgets.trader_overview import TraderOverview
from polymarket_tui.ui.widgets.trades_table import TradesTable
from polymarket_tui.ui.widgets.vim_table import VimDataTable

BOOK_POLL_SECONDS = 3.0


class MarketScreen(Screen):
    AUTO_FOCUS = None  # the order panel's inputs must not grab focus while hidden

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "toggle_outcome", "yes/no"),
        Binding("y", "select_outcome(0)", "yes", show=False),
        Binding("n", "select_outcome(1)", "no", show=False),
        Binding("b", "order('BUY')", "buy"),
        Binding("s", "order('SELL')", "sell"),
        Binding("a", "toggle_trades", "trades"),
        Binding("c", "toggle_activity('comments')", "comments"),
        Binding("tab", "cycle_interval(1)", "timeframe"),
        Binding("shift+tab", "cycle_interval(-1)", "prev timeframe", show=False),
        Binding("R", "related", "related", show=False, key_display="R"),
        Binding("e", "open_event", "event", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(
        self,
        market: Market,
        event: Event | None = None,
        order_side: str | None = None,
    ) -> None:
        super().__init__()
        self._market = market
        self._event = event
        self._outcome_index = 0  # 0 = YES/first outcome, 1 = NO
        self._interval = "1H"  # matches the initially-active interval tab
        self._history: list = []
        self._book = None
        self._trades_expanded = False
        self._pending_order_side = order_side  # open the order panel once the book arrives

    def compose(self) -> ComposeResult:
        yield AppHeader("market")
        yield Static(self._title_line(), classes="screen-title", id="market-title")
        with Horizontal(id="market-body"):
            with Vertical(id="market-left"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="outcomes-table")
                yield Static(id="position-line")
            with Vertical(id="book-pane"):
                yield Static(self._book_header(), id="book-title")
                scroll = VerticalScroll(BookPanel(id="book"), id="book-scroll")
                scroll.can_focus = False
                yield scroll
                yield OrderPanel(id="order-panel")
            with Vertical(id="trades-rail"):
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
            yield ActivityPanel(id="comments-panel")
        yield Static(self._info_line(), id="market-info", classes="subtle")
        yield Footer()

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
            bits.append(f"ends {fmt.end_date(m.end_date)}")
        if self._event and self._event.title.strip() != m.question.strip():
            bits.append(self._event.title.strip()[:30])
        return "  |  ".join(bits)

    def _fill_outcomes(self) -> None:
        """Outcome rows exactly like the event page; the cursor is the selector."""
        m = self._market
        table = self.query_one("#outcomes-table", VimDataTable)
        table.clear()
        yes = m.yes_price
        change = m.one_day_price_change
        spread = m.spread
        for idx, label in enumerate((m.outcomes or ["Yes", "No"])[:2]):
            price = yes if idx == 0 else (None if yes is None else 1 - yes)
            bid = m.best_bid if idx == 0 else (None if m.best_ask is None else 1 - m.best_ask)
            ask = m.best_ask if idx == 0 else (None if m.best_bid is None else 1 - m.best_bid)
            delta = change if idx == 0 else (None if change is None else -change)
            table.add_row(
                Text(label, style="bold green" if idx == 0 else "bold red"),
                Text(fmt.cents(price), style="bold cyan"),
                change_text(delta),
                Text(fmt.cents(bid), style="green"),
                Text(fmt.cents(ask), style="red"),
                fmt.cents(spread),
                fmt.money(m.volume_24hr),
                key=str(idx),
            )

    def on_data_table_row_highlighted(self, event) -> None:
        if event.data_table.id == "trades-table":
            if self._trades_expanded:
                self._refresh_trade_overview()
            return
        if event.data_table.id != "outcomes-table" or event.cursor_row is None:
            return
        self._apply_outcome(event.cursor_row)

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "outcomes-table":
            self.action_order("BUY")
        elif event.data_table.id == "trades-table":
            trader = self.query_one(TradesTable).trader_at_cursor()
            if trader is not None:
                from polymarket_tui.ui.screens.user import UserScreen

                self.app.push_screen(UserScreen(*trader))

    def _apply_outcome(self, index: int) -> None:
        if index == self._outcome_index:
            return
        self._outcome_index = index
        self._book = None  # stale: belongs to the other outcome until load_book returns
        self.query_one(OrderPanel).set_outcome(self._outcome_index)
        self.query_one("#book-title", Static).update(self._book_header())
        self.query_one(BookPanel).update("loading book...")
        self.load_book()
        self.load_history()

    def on_vim_data_table_bottom_reached(self, message) -> None:
        self.action_inspect_chart()

    def _book_header(self) -> str:
        return f"ORDER BOOK - {self._outcome_label().upper()}  (space to flip)"

    def _info_line(self) -> str:
        m = self._market
        bits = []
        if m.volume_24hr is not None:
            bits.append(f"vol24h {fmt.money(m.volume_24hr)}")
        if m.liquidity is not None:
            bits.append(f"liquidity {fmt.money(m.liquidity)}")
        if m.order_price_min_tick_size:
            bits.append(f"tick {m.order_price_min_tick_size}")
        if m.order_min_size:
            bits.append(f"min size {m.order_min_size:.0f}")
        bits.append(f"book refresh {BOOK_POLL_SECONDS:.0f}s")
        return "  |  ".join(bits)

    # -- lifecycle ----------------------------------------------------------

    def on_resize(self) -> None:
        if not self._trades_expanded:
            self.query_one("#trades-rail").display = self.size.width >= 170

    def on_mount(self) -> None:
        self.title = "market"
        table = self.query_one("#outcomes-table", VimDataTable)
        table.add_column("Outcome", width=24, key="outcome")
        table.add_column("Price", width=7, key="price")
        table.add_column("24h", width=7, key="change")
        table.add_column("Bid", width=7, key="bid")
        table.add_column("Ask", width=7, key="ask")
        table.add_column("Spread", width=7, key="spread")
        table.add_column("Vol 24h", width=9, key="vol")
        self._fill_outcomes()
        table.focus()
        self.query_one(ActivityPanel).configure(self._market, self._event)
        self.load_trades()
        self.set_interval(5.0, self.load_trades)
        self.load_book()
        self.load_history()
        self.load_position()
        self.set_interval(BOOK_POLL_SECONDS, self.load_book)

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
                style="bold green" if p.outcome.lower() == "yes" else "bold red",
            )
            out.append(f"@ {fmt.cents(p.avg_price)} ", style="dim")
            out.append(f"now {fmt.cents(p.cur_price)}  ")
            pnl_style = "green" if p.cash_pnl > 0 else "red" if p.cash_pnl < 0 else "dim"
            out.append(f"{p.cash_pnl:+,.2f} ({p.percent_pnl:+.0f}%)", style=pnl_style)
        line.update(out)

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
        try:
            book = await self.app.clob.order_book(token)
        except Exception as exc:
            panel.show_error(f"book unavailable: {exc}")
            return
        self._book = book
        panel.update_book(book)
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
        self.query_one("#outcomes-table", VimDataTable).move_cursor(row=index)

    def action_toggle_outcome(self) -> None:
        self.action_select_outcome(1 - self._outcome_index)

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

    def action_inspect_chart(self) -> None:
        if self.query_one(PriceChartPanel).display:
            self.query_one(PriceChartPanel).enter_inspect(
                return_focus=self.query_one("#outcomes-table", VimDataTable)
            )

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

    def action_toggle_trades(self) -> None:
        self._set_trades_expanded(not self._trades_expanded)

    def _set_trades_expanded(self, expanded: bool) -> None:
        self._trades_expanded = expanded
        self.query_one("#market-left").display = not expanded
        self.query_one("#book-pane").display = not expanded
        self.query_one("#market-overview-pane").display = expanded
        rail = self.query_one("#trades-rail")
        rail.set_class(expanded, "expanded")
        table = self.query_one(TradesTable)
        table.compact = not expanded
        table.build_columns()
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
        """left/escape step out one level before leaving the screen."""
        panel = self.query_one(OrderPanel)
        if panel.is_open:
            panel.close()
            return True
        if self._trades_expanded:
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
            from polymarket_tui.ui.screens.event import EventScreen

            self.app.push_screen(EventScreen(self._event))
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
        from polymarket_tui.ui.screens.event import EventScreen

        self.app.push_screen(EventScreen(event))

    def action_related(self) -> None:
        if self._event is None:
            self.notify("No event context for this market", severity="warning")
            return
        from polymarket_tui.ui.screens.related import RelatedScreen

        self.app.push_screen(RelatedScreen(self._event))

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
        else:
            panel.open(self._market, Side(side), self._outcome_index, self._book)

    def action_toggle_watch(self) -> None:
        slug = self._event.slug if self._event else self._market.slug
        watched = self.app.watchlist.toggle(slug)
        self.notify("Watching" if watched else "Unwatched", timeout=2)
