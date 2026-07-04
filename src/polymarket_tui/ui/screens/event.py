"""Event detail: multi-outcome price chart plus all child markets.

Logic lives in EventPane (a widget) so NavHost can host it as the 70% child
of the drill split. EventScreen is a thin full-screen wrapper kept as a
fallback.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.preview import MarketPreview
from polymarket_tui.ui.widgets.price_chart import MAX_SERIES, PriceChartPanel
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class EventPane(Vertical):
    """Event detail body - hosted as a drill pane by NavHost."""

    header_title = "event"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "toggle_info", "rules"),
        Binding("tab", "cycle_interval(1)", "timeframe"),
        Binding("shift+tab", "cycle_interval(-1)", "prev timeframe", show=False),
        Binding("R", "related", "related", key_display="R"),
        Binding("b", "order('BUY')", "buy"),
        Binding("s", "order('SELL')", "sell"),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, event: Event, **kwargs) -> None:
        super().__init__(**kwargs)
        self._event = event
        self._show_info = False
        self._interval = "1D"

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title")
        with Horizontal(id="event-body"):
            yield VimDataTable(cursor_type="row", zebra_stripes=True, id="markets-table")
            pane = VerticalScroll(
                MarketPreview(id="market-preview"),
                Static(id="rules-panel"),
                id="preview-pane",
            )
            pane.can_focus = False
            yield pane
        with Vertical(id="event-chart-pane"):
            tabs = Tabs(*(Tab(k, id=f"iv-{k}") for k in INTERVALS), id="interval-tabs")
            tabs.can_focus = False
            yield tabs
            yield PriceChartPanel(id="event-chart")

    def focus_inner(self) -> None:
        self.query_one("#markets-table", DataTable).focus()

    def _title_line(self) -> str:
        e = self._event
        parts = [e.title.strip()]
        if e.volume_24hr:
            parts.append(f"vol24h {fmt.money(e.volume_24hr)}")
        if e.end_date:
            parts.append(f"ends {fmt.end_date(e.end_date)}")
        series = e.primary_series
        if series is not None:
            recurrence = f" {series.recurrence}" if series.recurrence else ""
            parts.append(f"series: {series.title}{recurrence} (R)")
        elif e.tags:
            parts.append("/".join(t.label for t in e.tags[:3]))
        return "  |  ".join(parts)

    def action_order(self, side: str) -> None:
        """Jump into the highlighted outcome's market with the order panel open."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        market = self._market_by_slug(str(row_key.value))
        if market is None:
            return
        if not self.app.settings.can_auth:
            self.app.notify(
                "Trading needs a private key + funder - press A to authenticate",
                severity="warning",
            )
            return
        self.app.open_market(market, self._event, order_side=side)

    def action_related(self) -> None:
        from polymarket_tui.ui.screens.related import RelatedScreen

        self.app.push_screen(RelatedScreen(self._event))

    def on_mount(self) -> None:
        self.query_one("#rules-panel", Static).display = False
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
                fmt.trunc(market.display_title, 40),
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

    def action_cycle_interval(self, delta: int) -> None:
        keys = list(INTERVALS)
        idx = (keys.index(self._interval) + delta) % len(keys)
        self.action_set_interval_key(keys[idx])

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs.id == "interval-tabs" and event.tab.id:
            key = event.tab.id.removeprefix("iv-")
            if key != self._interval:
                self._interval = key
                self.load_chart()

    def on_vim_data_table_bottom_reached(self, message) -> None:
        # The chart lives below the table now - down past the last row inspects it.
        self.action_inspect_chart()

    def action_inspect_chart(self) -> None:
        pane = self.query_one("#event-chart-pane", Vertical)
        if pane.display:
            self.query_one(PriceChartPanel).enter_inspect(return_focus=self.query_one(VimDataTable))

    def action_toggle_info(self) -> None:
        """Swap the right pane between the market preview and the event rules."""
        rules = self.query_one("#rules-panel", Static)
        preview = self.query_one(MarketPreview)
        self._show_info = not self._show_info
        rules.display = self._show_info
        preview.display = not self._show_info
        if self._show_info:
            out = Text()
            out.append("RULES\n\n", style="bold")
            out.append(self._event.description.strip() or "(no description)")
            rules.update(out)

    def action_refresh(self) -> None:
        self.refresh_event()
        self.load_chart()


class EventScreen(Screen):
    """Thin full-screen wrapper around EventPane (fallback / standalone)."""

    BINDINGS = [Binding("escape", "app.pop_screen", "back")]

    def __init__(self, event: Event) -> None:
        super().__init__()
        self._event = event

    def compose(self) -> ComposeResult:
        yield AppHeader("event")
        yield EventPane(self._event)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "event"
