"""Market detail: live-polling order book + price history chart."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.book_panel import BookPanel
from polymarket_tui.ui.widgets.price_chart import PriceChartPanel

BOOK_POLL_SECONDS = 3.0


class MarketScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("t", "toggle_outcome", "yes/no"),
        Binding("r", "refresh", "refresh"),
        Binding("W", "toggle_watch", "watch", key_display="W"),
        Binding("x", "inspect_chart", "inspect"),
        Binding("b", "order('BUY')", "buy"),
        Binding("s", "order('SELL')", "sell"),
        Binding("R", "related", "related", show=False, key_display="R"),
        Binding("tab", "cycle_interval(1)", "interval"),
        Binding("shift+tab", "cycle_interval(-1)", "prev interval", show=False),
        Binding("l", "cycle_interval(1)", "next interval", show=False),
        Binding("h", "cycle_interval(-1)", "prev interval", show=False),
    ] + [
        Binding(str(i + 1), f"set_interval_key('{key}')", key, show=i == 0)
        for i, key in enumerate(INTERVALS)
    ]

    def __init__(self, market: Market, event: Event | None = None) -> None:
        super().__init__()
        self._market = market
        self._event = event
        self._outcome_index = 0  # 0 = YES/first outcome, 1 = NO
        self._interval = "1H"  # matches the initially-active interval tab
        self._history: list = []
        self._book = None

    def compose(self) -> ComposeResult:
        yield AppHeader("market")
        yield Static(self._title_line(), classes="screen-title", id="market-title")
        with Vertical(id="market-body-wrap"):
            with Horizontal(id="market-body"):
                with Vertical(id="chart-pane"):
                    tabs = Tabs(*(Tab(k, id=f"iv-{k}") for k in INTERVALS), id="interval-tabs")
                    tabs.can_focus = False
                    yield tabs
                    yield PriceChartPanel(id="price-chart")
                with Vertical(id="book-pane"):
                    yield Static(self._book_header(), id="book-title")
                    scroll = VerticalScroll(BookPanel(id="book"), id="book-scroll")
                    scroll.can_focus = False
                    yield scroll
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
        if m.yes_price is not None:
            bits.append(f"YES {fmt.cents(m.yes_price)}")
        if m.end_date:
            bits.append(f"ends {fmt.end_date(m.end_date)}")
        if self._event and self._event.title.strip() != m.question.strip():
            bits.append(self._event.title.strip()[:30])
        return "  |  ".join(bits)

    def _book_header(self) -> str:
        return f"ORDER BOOK - {self._outcome_label().upper()}  (t to flip)"

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

    def on_mount(self) -> None:
        self.title = "market"
        self.load_book()
        self.load_history()
        self.load_position()
        self.set_interval(BOOK_POLL_SECONDS, self.load_book)

    @work(exclusive=True, group="position")
    async def load_position(self) -> None:
        """Show the user's position in this market on the info line, if any."""
        app = self.app
        if not app.settings.can_read_portfolio:
            return
        try:
            positions = await app.portfolio.positions()
        except Exception:
            return
        tokens = set(self._market.clob_token_ids)
        mine = [p for p in positions if p.asset in tokens and p.size >= 0.01]
        if not mine:
            return
        bits = []
        for p in mine:
            bits.append(
                f"your position: {p.size:,.0f} {p.outcome} @ {fmt.cents(p.avg_price)}"
                f" (now {fmt.cents(p.cur_price)}, P&L {p.cash_pnl:+,.2f})"
            )
        info = self.query_one("#market-info", Static)
        info.update("  |  ".join(bits) + "\n" + self._info_line())

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

    def action_toggle_outcome(self) -> None:
        self._outcome_index = 1 - self._outcome_index
        self._book = None  # stale: belongs to the other outcome until load_book returns
        self.query_one("#book-title", Static).update(self._book_header())
        self.query_one(BookPanel).update("loading book...")
        self.load_book()
        self.load_history()

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
        self.query_one(PriceChartPanel).enter_inspect()

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
        from polymarket_tui.ui.screens.order_modal import OrderModal

        app.push_screen(
            OrderModal(
                self._market,
                self._event,
                self._outcome_index,
                Side(side),
                self._book,
            )
        )

    def action_toggle_watch(self) -> None:
        slug = self._event.slug if self._event else self._market.slug
        watched = self.app.watchlist.toggle(slug)
        self.notify("Watching" if watched else "Unwatched", timeout=2)
