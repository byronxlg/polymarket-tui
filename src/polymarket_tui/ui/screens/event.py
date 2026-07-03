"""Event detail: multi-outcome price chart plus all child markets."""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.preview import MarketPreview
from polymarket_tui.ui.widgets.price_chart import MAX_SERIES, PriceChartPanel
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class EventScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("W", "toggle_watch", "watch", key_display="W"),
        Binding("i", "toggle_info", "rules"),
        Binding("r", "refresh", "refresh"),
        Binding("c", "toggle_chart", "chart"),
    ] + [
        Binding(str(i + 1), f"set_interval_key('{key}')", key, show=False)
        for i, key in enumerate(INTERVALS)
    ]

    def __init__(self, event: Event) -> None:
        super().__init__()
        self._event = event
        self._show_info = False
        self._interval = "1D"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._title_line(), classes="screen-title")
        with Vertical(id="event-chart-pane"):
            tabs = Tabs(*(Tab(k, id=f"iv-{k}") for k in INTERVALS), id="interval-tabs")
            tabs.can_focus = False
            yield tabs
            yield PriceChartPanel(id="event-chart")
        with Horizontal(id="event-body"):
            yield VimDataTable(cursor_type="row", zebra_stripes=True, id="markets-table")
            pane = VerticalScroll(MarketPreview(id="market-preview"), id="preview-pane")
            pane.can_focus = False
            yield pane
        yield Static(id="event-info", classes="subtle")
        yield Footer()

    def _title_line(self) -> str:
        e = self._event
        parts = [e.title.strip()]
        if e.volume_24hr:
            parts.append(f"vol24h {fmt.money(e.volume_24hr)}")
        if e.end_date:
            parts.append(f"ends {fmt.end_date(e.end_date)}")
        if e.tags:
            parts.append("/".join(t.label for t in e.tags[:3]))
        return "  |  ".join(parts)

    def on_mount(self) -> None:
        self.title = "event"
        info = self.query_one("#event-info", Static)
        info.display = False
        self.query_one("#interval-tabs", Tabs).active = f"iv-{self._interval}"
        table = self.query_one(DataTable)
        table.add_column("Outcome", width=40, key="outcome")
        table.add_column("Price", width=7, key="price")
        table.add_column("24h", width=7, key="change")
        table.add_column("Bid", width=7, key="bid")
        table.add_column("Ask", width=7, key="ask")
        table.add_column("Spread", width=7, key="spread")
        table.add_column("Vol 24h", width=9, key="vol")
        table.focus()
        self._fill_table()
        self.load_chart()
        self.refresh_event()

    def _fill_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for market in self._event.active_markets:
            table.add_row(
                market.display_title[:40],
                Text(fmt.cents(market.yes_price), style="bold cyan"),
                change_text(market.one_day_price_change),
                Text(fmt.cents(market.best_bid), style="green"),
                Text(fmt.cents(market.best_ask), style="red"),
                fmt.cents(market.spread),
                fmt.money(market.volume_24hr),
                key=market.slug,
            )
        markets = self._event.active_markets
        self.query_one(MarketPreview).show_market(markets[0] if markets else None)

    def _market_by_slug(self, slug: str | None):
        if not slug:
            return None
        return next((m for m in self._event.active_markets if m.slug == slug), None)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            market = self._market_by_slug(str(event.row_key.value))
            if market is not None:
                self.query_one(MarketPreview).show_market(market)

    # -- chart -----------------------------------------------------------------

    def _chart_markets(self):
        """Top outcomes by price, chart-worthy ones first."""
        ms = [m for m in self._event.active_markets if m.token_id(0)]
        return sorted(ms, key=lambda m: m.yes_price or 0, reverse=True)[:MAX_SERIES]

    @work(exclusive=True, group="chart")
    async def load_chart(self) -> None:
        markets = self._chart_markets()
        panel = self.query_one(PriceChartPanel)
        results = await asyncio.gather(
            *(self.app.clob.prices_history(m.token_id(0), self._interval) for m in markets),
            return_exceptions=True,
        )
        series = [
            (m.display_title, pts)
            for m, pts in zip(markets, results, strict=True)
            if not isinstance(pts, BaseException)
        ]
        panel.show(series, self._interval)

    @work(exclusive=True)
    async def refresh_event(self) -> None:
        try:
            fresh = await self.app.gamma.event_by_slug(self._event.slug)
        except Exception as exc:
            self.notify(f"Refresh failed: {exc}", severity="error")
            return
        if fresh is not None:
            self._event = fresh
            self._fill_table()

    # -- actions ------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        slug = str(event.row_key.value)
        market = next((m for m in self._event.active_markets if m.slug == slug), None)
        if market is not None:
            self.app.open_market(market, self._event)

    def action_set_interval_key(self, key: str) -> None:
        self._interval = key
        self.query_one("#interval-tabs", Tabs).active = f"iv-{key}"
        self.load_chart()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs.id == "interval-tabs" and event.tab.id:
            key = event.tab.id.removeprefix("iv-")
            if key != self._interval:
                self._interval = key
                self.load_chart()

    def action_toggle_chart(self) -> None:
        pane = self.query_one("#event-chart-pane", Vertical)
        pane.display = not pane.display

    def action_toggle_watch(self) -> None:
        watched = self.app.watchlist.toggle(self._event.slug)
        self.notify("Watching" if watched else "Unwatched", timeout=2)

    def action_toggle_info(self) -> None:
        info = self.query_one("#event-info", Static)
        self._show_info = not self._show_info
        info.display = self._show_info
        if self._show_info:
            desc = self._event.description or "(no description)"
            info.update(desc[:1200])

    def action_refresh(self) -> None:
        self.refresh_event()
        self.load_chart()
