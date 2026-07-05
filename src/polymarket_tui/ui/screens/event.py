"""Event detail: multi-outcome price chart plus all child markets.

Logic lives in EventPane (a widget) so NavHost can host it as the 70% child
of the drill split.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Static, Tab, Tabs

from polymarket_tui.api.clob import INTERVALS
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.theme import BLUE, DOWN, UP
from polymarket_tui.ui.tiers import ColumnSpec, Tier, TierAware, effective_tier, fit_columns
from polymarket_tui.ui.widgets.activity_panel import ActivityPanel
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.preview import MarketPreview
from polymarket_tui.ui.widgets.price_chart import MAX_SERIES, PriceChartPanel
from polymarket_tui.ui.widgets.vim_table import VimDataTable

# (key, label, width) per width tier: medium drops Spread so the table plus
# preview rail fit in the 70% slot; compact keeps outcome + price + 24h only.
MARKETS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("outcome", "Outcome", 40),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("bid", "Bid", 7),
        ("ask", "Ask", 7),
        ("spread", "Spread", 7),
        ("vol", "Vol 24h", 9),
    ),
    "medium": (
        ("outcome", "Outcome", 34),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("bid", "Bid", 7),
        ("ask", "Ask", 7),
        ("vol", "Vol 24h", 9),
    ),
    "compact": (
        ("outcome", "Outcome", 26),
        ("price", "Price", 7),
        ("change", "24h", 7),
    ),
}


class EventPane(TierAware, Vertical):
    """Event detail body - hosted as a drill pane by NavHost."""

    header_title = "event"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "toggle_info", "rules"),
        Binding("c", "toggle_activity('comments')", "comments", show=False),
        Binding("tab", "cycle_interval(1)", "timeframe"),
        Binding("shift+tab", "cycle_interval(-1)", "prev timeframe", show=False),
        Binding("R", "related", "related", key_display="R"),
        Binding("b", "order('BUY')", "buy"),
        Binding("s", "order('SELL')", "sell"),
        Binding("O", "open_web", "web", show=False, key_display="O"),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, event: Event, **kwargs) -> None:
        super().__init__(**kwargs)
        self._event = event
        self._show_info = False
        self._interval = "ALL"
        self._columns_spec: list[ColumnSpec] = list(MARKETS_TIER_COLUMNS["full"])
        self.drill_key = ("event", event.slug)

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
            yield ActivityPanel(id="event-comments-panel")

    def focus_inner(self) -> None:
        self.query_one("#markets-table", DataTable).focus()

    def _title_line(self) -> str:
        e = self._event
        parts = [e.title.strip()]
        if e.volume_24hr:
            parts.append(f"vol24h {fmt.vol(e.volume_24hr)}")
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
        self.app.open_related(self._event)

    def action_open_web(self) -> None:
        import webbrowser

        url = f"https://polymarket.com/event/{self._event.slug}"
        webbrowser.open(url)
        self.notify(f"Opened {url}", timeout=3)

    @property
    def _ordered_condition_ids(self) -> set[str]:
        app = self.app
        return app.portfolio.order_condition_ids() if app.settings.can_auth else set()

    @work(exclusive=True, group="own-orders")
    async def load_own_orders(self) -> None:
        """Refresh the cached open orders, then re-mark the outcome rows."""
        try:
            await self.app.portfolio.open_orders()
        except Exception:
            return
        if self._ordered_condition_ids:
            table = self.query_one(DataTable)
            cursor = table.cursor_row
            self._fill_table()
            if cursor is not None and table.row_count:
                table.move_cursor(row=min(cursor, table.row_count - 1))

    def on_mount(self) -> None:
        self.query_one("#rules-panel", Static).display = False
        self.query_one("#interval-tabs", Tabs).active = f"iv-{self._interval}"
        self._columns_spec = list(MARKETS_TIER_COLUMNS[self.tier])
        self._build_columns()
        self.query_one(DataTable).focus()
        self._fill_table()
        self.query_one(ActivityPanel).configure(None, self._event)
        self.load_chart()
        self.refresh_event()
        self.load_own_orders()
        self.set_interval(15.0, self.load_own_orders)
        self.tier_ready()
        self._schedule_refit()

    def _build_columns(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        for key, label, width in self._columns_spec:
            table.add_column(label, width=width, key=key)

    def on_tier_changed(self, tier: Tier) -> None:
        self._schedule_refit()

    def on_resize(self) -> None:
        if self._tier_ready:
            self._schedule_refit()

    def _schedule_refit(self) -> None:
        # Measure after layout settles: the slot tier is a cap, the column
        # set follows the table's real width.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        table = self.query_one(DataTable)
        width = table.size.width
        if width <= 0 or not table.columns:
            return
        tier = effective_tier(self.tier, width, MARKETS_TIER_COLUMNS)
        titles = [m.display_title for m in self._event.active_markets]
        flex_max = max((len(t) for t in titles), default=0) or None
        spec = fit_columns(MARKETS_TIER_COLUMNS[tier], width, "outcome", flex_max)
        if spec == self._columns_spec:
            return
        self._columns_spec = spec
        cursor = table.cursor_row
        self._build_columns()
        self._fill_table()
        if cursor is not None and table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))

    def _fill_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        columns = self._columns_spec
        outcome_width = dict((k, w) for k, _, w in columns)["outcome"]
        ordered = self._ordered_condition_ids
        for market in self._event.active_markets:
            # Constant-width flag prefix so titles don't shift when a resting
            # order appears ('o' = you have an open order on this outcome).
            title = fmt.trunc(market.display_title, outcome_width - 2)
            if market.condition_id in ordered:
                outcome_cell = Text("o ", style=f"bold {BLUE}")
            else:
                outcome_cell = Text("  ")
            outcome_cell.append(title)
            cells = {
                "outcome": outcome_cell,
                "price": Text(fmt.cents(market.yes_price), style="bold"),
                "change": change_text(market.one_day_price_change),
                "bid": Text(fmt.cents(market.best_bid), style=UP),
                "ask": Text(fmt.cents(market.best_ask), style=DOWN),
                "spread": fmt.cents(market.spread),
                "vol": fmt.vol(market.volume_24hr),
            }
            table.add_row(*(cells[key] for key, _, _ in columns), key=market.slug)
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
            self.query_one(ActivityPanel).configure(None, fresh)
            self._schedule_refit()  # fresh titles may change the flex width

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

    def action_toggle_activity(self, mode: str) -> None:
        """c toggles comments into the chart strip; chart hides while shown."""
        panel = self.query_one(ActivityPanel)
        panel.toggle(mode)
        showing = panel.mode is not None
        self.query_one("#interval-tabs", Tabs).display = not showing
        self.query_one(PriceChartPanel).display = not showing

    def action_refresh(self) -> None:
        self.refresh_event()
        self.load_chart()
