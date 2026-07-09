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
from polymarket_tui.ui.follow import CursorFollow
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.theme import BLUE, DOWN, UP
from polymarket_tui.ui.tiers import (
    ColumnSpec,
    Tier,
    TierAware,
    effective_tier,
    fit_columns,
    usable_width,
)
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

# Spacious re-composes each outcome the way the home events table does: the
# bid/ask/spread/vol columns fold into a dim second line under the outcome
# title and the 24h change stacks under the price, freeing width for long
# outcome names.
MARKETS_SPACIOUS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("outcome", "Outcome", 46),
        ("price", "Price", 8),
    ),
    "medium": (
        ("outcome", "Outcome", 38),
        ("price", "Price", 8),
    ),
    "compact": (
        ("outcome", "Outcome", 26),
        ("price", "Price", 8),
    ),
}


def market_meta(market) -> str:
    """The dim second line of a spacious outcome row: bid 33c · ask 34c · vol $41M.

    Spread is dropped (it is just ask - bid) and the volume label is the bare
    'vol' so the value fits without truncating at the 70% pane width."""
    return (
        f"bid {fmt.cents(market.best_bid)} · ask {fmt.cents(market.best_ask)}"
        f" · vol {fmt.vol(market.volume_24hr)}"
    )


class EventPane(TierAware, Vertical):
    """Event detail body - hosted as a drill pane by NavHost."""

    header_title = "event"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "rules", "rules"),
        Binding("c", "comments", "comments", show=False),
        Binding("tab", "cycle_interval(1)", "timeframe"),
        Binding("shift+tab", "cycle_interval(-1)", "prev timeframe", show=False),
        Binding("r", "related", "related"),
        Binding("b", "order('BUY')", "buy"),
        Binding("s", "order('SELL')", "sell"),
        Binding("o", "open_web", "web", show=False),
    ]

    def __init__(self, event: Event, **kwargs) -> None:
        super().__init__(**kwargs)
        self._event = event
        self._interval = "ALL"
        self._rendered_density: str = "condensed"
        self._columns_spec: list[ColumnSpec] = list(MARKETS_TIER_COLUMNS["full"])
        # Throttled cursor-follow: one preview render per settle, not per row.
        self._preview_follow = CursorFollow(self, self._show_market_preview)
        self.drill_key = ("event", event.slug)

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title")
        with Horizontal(id="event-body"):
            yield VimDataTable(cursor_type="row", zebra_stripes=True, id="markets-table")
            pane = VerticalScroll(
                MarketPreview(id="market-preview"),
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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Compact hides the chart strip (tier CSS) - don't advertise or fire
        the timeframe cycle there. Comments and rules are pop-outs (overlays
        over the whole pane), so they stay available at every tier."""
        if self.tier == "compact" and action == "cycle_interval":
            return False
        return True

    def _title_line(self) -> str:
        e = self._event
        parts = [e.title.strip()]
        if e.volume_24hr:
            parts.append(f"vol24h {fmt.vol(e.volume_24hr)}")
        status = fmt.event_status(e)
        if status:
            parts.append(status)
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

    @property
    def _held_condition_ids(self) -> set[str]:
        """Markets here you hold a position in (observer mode counts too)."""
        app = self.app
        if not app.settings.can_read_portfolio:
            return set()
        return app.portfolio.position_condition_ids()

    @work(exclusive=True, group="own-orders")
    async def load_own_orders(self) -> None:
        """Refresh cached orders + positions, then re-mark the outcome rows."""
        app = self.app
        try:
            await app.portfolio.open_orders()
            if app.settings.can_read_portfolio:
                await app.portfolio.positions()
        except Exception:
            return
        if not alive(self):
            return  # pane torn down while we fetched
        if self._ordered_condition_ids or self._held_condition_ids:
            table = self.query_one(DataTable)
            cursor = table.cursor_row
            self._fill_table()
            if cursor is not None and table.row_count:
                table.move_cursor(row=min(cursor, table.row_count - 1))

    def _markets_columns(self) -> dict[Tier, tuple]:
        """Column sets for the current density (spacious re-composes rows)."""
        if self.app.density == "spacious":
            return MARKETS_SPACIOUS_TIER_COLUMNS
        return MARKETS_TIER_COLUMNS

    def on_mount(self) -> None:
        self.query_one("#interval-tabs", Tabs).active = f"iv-{self._interval}"
        self._rendered_density = self.app.density
        self._columns_spec = list(self._markets_columns()[self.tier])
        self._build_columns()
        self.query_one(DataTable).focus()
        self._fill_table()
        self.load_chart()
        self.refresh_event()
        self.load_own_orders()
        self.set_interval(15.0, self.load_own_orders)
        self.tier_ready()
        self._schedule_refit()

    def _build_columns(self) -> None:
        table = self.query_one(DataTable)
        table.cell_padding = 2 if self.app.density == "spacious" else 1
        table.clear(columns=True)
        for key, label, width in self._columns_spec:
            table.add_column(label, width=width, key=key)

    def on_tier_changed(self, tier: Tier) -> None:
        self._schedule_refit()
        self.refresh_bindings()  # the footer gates on tier (check_action)

    def on_density_changed(self, density: str) -> None:
        """T toggled: outcomes re-compose into two-line rows (app calls this)."""
        self._schedule_refit()

    def on_resize(self) -> None:
        if self._tier_ready:
            self._schedule_refit()

    def _schedule_refit(self) -> None:
        # Measure after layout settles: the slot tier is a cap, the column
        # set follows the table's real width.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        if not alive(self):
            return  # call_after_refresh can fire after the pane is torn down
        table = self.query_one(DataTable)
        width = usable_width(table)
        if width <= 0 or not table.columns:
            return
        columns = self._markets_columns()
        pad = 2 if self.app.density == "spacious" else 1
        tier = effective_tier(self.tier, width, columns, pad)
        titles = [m.display_title for m in self._event.active_markets]
        flex_max = max((len(t) for t in titles), default=0) or None
        spec = fit_columns(columns[tier], width, "outcome", flex_max, pad)
        if spec == self._columns_spec and self._rendered_density == self.app.density:
            return
        self._rendered_density = self.app.density
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
        spacious = self.app.density == "spacious"
        height = 2 if spacious else 1
        ordered = self._ordered_condition_ids
        held = self._held_condition_ids
        for market in self._event.active_markets:
            # Constant-width flag prefix so titles don't shift ('o' = you
            # have an open order here, '+' = you hold a position here).
            title = fmt.trunc(market.display_title, outcome_width - 3)
            outcome_cell = Text()
            outcome_cell.append(
                "o" if market.condition_id in ordered else " ", style=f"bold {BLUE}"
            )
            outcome_cell.append(
                "+" if market.condition_id in held else " ", style=f"bold {UP}"
            )
            outcome_cell.append(" ")
            outcome_cell.append(title)
            if spacious:
                # bid/ask/spread/vol fold into a dim line indented under the
                # title (3-char flag prefix); the 24h change stacks under price.
                outcome_cell.append(
                    "\n   " + fmt.trunc(market_meta(market), outcome_width - 3),
                    style="dim",
                )
                price_cell = Text(justify="right")
                price_cell.append(fmt.cents(market.yes_price), style="bold")
                price_cell.append("\n")
                price_cell.append_text(change_text(market.one_day_price_change))
                cells = {"outcome": outcome_cell, "price": price_cell}
            else:
                cells = {
                    "outcome": outcome_cell,
                    "price": Text(fmt.cents(market.yes_price), style="bold"),
                    "change": change_text(market.one_day_price_change),
                    "bid": Text(fmt.cents(market.best_bid), style=UP),
                    "ask": Text(fmt.cents(market.best_ask), style=DOWN),
                    "spread": fmt.cents(market.spread),
                    "vol": fmt.vol(market.volume_24hr),
                }
            table.add_row(
                *(cells[key] for key, _, _ in columns), key=market.slug, height=height
            )
        markets = self._event.active_markets
        self.query_one(MarketPreview).show_market(markets[0] if markets else None)

    def _market_by_slug(self, slug: str | None):
        if not slug:
            return None
        return next((m for m in self._event.active_markets if m.slug == slug), None)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            self._preview_follow(str(event.row_key.value))

    def _show_market_preview(self, slug: str) -> None:
        market = self._market_by_slug(slug)
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
        if not alive(self):
            return  # pane torn down while we fetched
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
        if fresh is None or not alive(self):
            return
        # R must not snap the cursor to the top (the 15s own-orders interval
        # already preserves it) - restore by slug key across the rebuild.
        table = self.query_one(DataTable)
        keep: str | None = None
        if table.cursor_row is not None and table.row_count:
            keep = str(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        self._event = fresh
        self._fill_table()
        if keep is not None and any(m.slug == keep for m in fresh.active_markets):
            table.move_cursor(row=table.get_row_index(keep))
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

    def action_rules(self) -> None:
        """space opens the event's resolution rules in a reading pop-out."""
        body = (self._event.description or "").strip()
        self.app.open_rules(f"RULES - {self._event.title.strip()}", body)

    def action_comments(self) -> None:
        """c opens the event's comment thread in a reading pop-out."""
        self.app.open_comments(self._event)

    def action_refresh(self) -> None:
        """The global r: event data, chart, and the order/holding flags."""
        self.refresh_event()
        self.load_chart()
        self.load_own_orders()
