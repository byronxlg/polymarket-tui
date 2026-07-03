"""Event detail: all child markets with prices, opens the market screen."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.event_table import change_text
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class EventScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("W", "toggle_watch", "watch", key_display="W"),
        Binding("i", "toggle_info", "rules"),
        Binding("r", "refresh", "refresh"),
    ]

    def __init__(self, event: Event) -> None:
        super().__init__()
        self._event = event
        self._show_info = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._title_line(), classes="screen-title")
        yield VimDataTable(cursor_type="row", zebra_stripes=True, id="markets-table")
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        slug = str(event.row_key.value)
        market = next((m for m in self._event.active_markets if m.slug == slug), None)
        if market is not None:
            self.app.open_market(market, self._event)

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
