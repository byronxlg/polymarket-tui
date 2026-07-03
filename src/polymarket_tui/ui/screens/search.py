"""Search screen: debounced Gamma public-search over events."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Input

from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser

DEBOUNCE_SECONDS = 0.35


class SearchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back_or_pop", "back"),
        Binding("W", "toggle_watch", "watch", key_display="W"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._timer = None

    def compose(self) -> ComposeResult:
        yield AppHeader("search")
        yield Input(placeholder="search markets... (esc to go back)", id="search-input")
        yield EventsBrowser(id="search-browser")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "search"
        self.query_one(Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._timer is not None:
            self._timer.stop()
        query = event.value.strip()
        if len(query) < 2:
            return
        self._timer = self.set_timer(DEBOUNCE_SECONDS, lambda: self.run_search(query))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        table = self.query_one(EventsTable)
        if table.row_count:
            table.focus()

    @work(exclusive=True)
    async def run_search(self, query: str) -> None:
        try:
            events = await self.app.gamma.search(query)
        except Exception as exc:
            self.notify(f"Search failed: {exc}", severity="error")
            return
        events = [e for e in events if e.top_market is not None]
        self.query_one(EventsTable).set_events(events, set(self.app.watchlist.slugs))

    def on_data_table_row_selected(self, event) -> None:
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def action_toggle_watch(self) -> None:
        table = self.query_one(EventsTable)
        if not table.has_focus:
            return
        selected = table.highlighted_event()
        if selected is None:
            return
        watched = self.app.watchlist.toggle(selected.slug)
        table.set_star(selected.slug, watched)

    def action_back_or_pop(self) -> None:
        # esc from the results table goes back to the input; from the input, pops.
        if self.query_one(EventsTable).has_focus:
            self.query_one(Input).focus()
        else:
            self.app.pop_screen()
