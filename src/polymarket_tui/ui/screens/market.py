"""Market detail: live-polling order book + price history chart."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.widgets.book_panel import BookPanel
from polymarket_tui.ui.widgets.price_chart import PriceChartPanel

BOOK_POLL_SECONDS = 3.0


class MarketScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("t", "toggle_outcome", "yes/no"),
        Binding("r", "refresh", "refresh"),
        Binding("W", "toggle_watch", "watch", key_display="W"),
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

    def compose(self) -> ComposeResult:
        yield Header()
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
        self.set_interval(BOOK_POLL_SECONDS, self.load_book)

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
        self.query_one("#book-title", Static).update(self._book_header())
        self.query_one(BookPanel).update("loading book...")
        self.load_book()
        self.load_history()

    def action_set_interval_key(self, key: str) -> None:
        self._interval = key
        tabs = self.query_one("#interval-tabs", Tabs)
        tabs.active = f"iv-{key}"
        self.load_history()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs.id == "interval-tabs" and event.tab.id:
            key = event.tab.id.removeprefix("iv-")
            if key != self._interval:
                self._interval = key
                self.load_history()

    def action_refresh(self) -> None:
        self.load_book()
        self.load_history()

    def action_toggle_watch(self) -> None:
        slug = self._event.slug if self._event else self._market.slug
        watched = self.app.watchlist.toggle(slug)
        self.notify("Watching" if watched else "Unwatched", timeout=2)
