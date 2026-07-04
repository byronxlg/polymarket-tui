"""Search screen: debounced Gamma public-search with combobox navigation.

Arrows drive the result list while focus stays in the input (fzf-style):
type to filter, up/down to pick, enter to open, escape to leave.
"""

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


class SearchInput(Input):
    """Up/down move the result cursor without leaving the input."""

    BINDINGS = [
        Binding("down", "move_result(1)", "next result", show=False),
        Binding("up", "move_result(-1)", "prev result", show=False),
    ]

    def action_move_result(self, delta: int) -> None:
        table = self.screen.query_one(EventsTable)
        if table.row_count == 0:
            return
        row = table.cursor_row if table.cursor_row is not None else -1
        table.move_cursor(row=max(0, min(table.row_count - 1, row + delta)))


class SearchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back_or_pop", "back"),
        Binding("space", "toggle_watch", "star", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._timer = None

    def compose(self) -> ComposeResult:
        yield AppHeader("search")
        yield SearchInput(
            placeholder="search markets... (up/down pick, enter open)", id="search-input"
        )
        yield EventsBrowser(id="search-browser")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "search"
        self.query_one(SearchInput).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._timer is not None:
            self._timer.stop()
        query = event.value.strip()
        if len(query) < 2:
            return
        self._timer = self.set_timer(DEBOUNCE_SECONDS, lambda: self.run_search(query))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter opens the highlighted result straight from the input.
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    @work(exclusive=True)
    async def run_search(self, query: str) -> None:
        try:
            events = await self.app.gamma.search(query)
        except Exception as exc:
            self.notify(f"Search failed: {exc}", severity="error")
            return
        events = [e for e in events if e.top_market is not None]
        table = self.query_one(EventsTable)
        table.set_events(events, set(self.app.watchlist.slugs))
        browser = self.query_one(EventsBrowser)
        browser.preview.show_event(events[0] if events else None)

    def on_data_table_row_selected(self, event) -> None:
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def action_toggle_watch(self) -> None:
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is None:
            return
        watched = self.app.watchlist.toggle(selected.slug)
        self.query_one(EventsTable).set_star(selected.slug, watched)

    def action_back_or_pop(self) -> None:
        self.app.pop_screen()
