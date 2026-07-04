"""Search screen: debounced Gamma public-search with combobox navigation.

Arrows drive the result list while focus stays in the input (fzf-style):
type to filter, up/down to pick, enter to open, escape to leave.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import Profile
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser
from polymarket_tui.ui.widgets.vim_table import VimDataTable

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
        if delta > 0 and row >= table.row_count - 1:
            # Past the last event: continue into the traders section.
            traders = self.screen.query_one("#traders-table")
            if traders.display and traders.row_count:
                traders.focus()
                return
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
            placeholder="search markets and traders... (up/down pick, enter open)",
            id="search-input",
        )
        yield EventsBrowser(id="search-browser")
        yield Static(" TRADERS", classes="screen-title", id="traders-title")
        yield VimDataTable(cursor_type="row", zebra_stripes=True, id="traders-table")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "search"
        self._profiles: list[Profile] = []
        traders = self.query_one("#traders-table", VimDataTable)
        traders.add_column("Trader", width=30, key="name")
        traders.add_column("Address", width=16, key="address")
        traders.add_column("Bio", width=60, key="bio")
        self._set_traders_visible(False)
        self.query_one(SearchInput).focus()

    def _set_traders_visible(self, visible: bool) -> None:
        self.query_one("#traders-title", Static).display = visible
        self.query_one("#traders-table", VimDataTable).display = visible

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
            events, profiles = await self.app.gamma.search(query)
        except Exception as exc:
            self.notify(f"Search failed: {exc}", severity="error")
            return
        events = [e for e in events if e.top_market is not None]
        table = self.query_one(EventsTable)
        table.set_events(events, set(self.app.watchlist.slugs))
        browser = self.query_one(EventsBrowser)
        browser.preview.show_event(events[0] if events else None)

        self._profiles = profiles[:5]
        traders = self.query_one("#traders-table", VimDataTable)
        traders.clear()
        for prof in self._profiles:
            star = "*" if self.app.watchlist.is_watched_user(prof.proxy_wallet) else " "
            traders.add_row(
                star + " " + fmt.trunc(prof.display_name, 27),
                f"{prof.proxy_wallet[:6]}...{prof.proxy_wallet[-4:]}",
                fmt.trunc(prof.bio or "", 60),
                key=prof.proxy_wallet,
            )
        self._set_traders_visible(bool(self._profiles))

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "traders-table":
            self._open_trader()
            return
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def _open_trader(self) -> None:
        traders = self.query_one("#traders-table", VimDataTable)
        if traders.cursor_row is None or traders.row_count == 0:
            return
        address = str(traders.coordinate_to_cell_key((traders.cursor_row, 0)).row_key.value)
        profile = next((p for p in self._profiles if p.proxy_wallet == address), None)
        if profile is not None:
            from polymarket_tui.ui.screens.user import UserScreen

            self.app.push_screen(UserScreen(address, profile.display_name))

    def on_vim_data_table_bottom_reached(self, message) -> None:
        # events table -> traders table below it
        if message.table.id == "events-table" and self._profiles:
            self.query_one("#traders-table", VimDataTable).focus()

    def on_vim_data_table_top_reached(self, message) -> None:
        # Up from the traders section or the events list returns to the input.
        self.query_one(SearchInput).focus()

    def action_toggle_watch(self) -> None:
        traders = self.query_one("#traders-table", VimDataTable)
        if traders.has_focus:
            if traders.cursor_row is None or traders.row_count == 0:
                return
            address = str(traders.coordinate_to_cell_key((traders.cursor_row, 0)).row_key.value)
            profile = next((p for p in self._profiles if p.proxy_wallet == address), None)
            if profile is None:
                return
            watched = self.app.watchlist.toggle_user(address, profile.display_name)
            traders.update_cell(
                address,
                "name",
                ("*" if watched else " ") + " " + fmt.trunc(profile.display_name, 27),
            )
            return
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is None:
            return
        watched = self.app.watchlist.toggle(selected.slug)
        self.query_one(EventsTable).set_star(selected.slug, watched)

    def action_back_or_pop(self) -> None:
        self.app.pop_screen()
