"""Watchlist: starred events and followed traders."""

from __future__ import annotations

import asyncio

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static, TabbedContent, TabPane

from polymarket_tui.core import fmt
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class WatchlistScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("space", "toggle_watch", "unstar"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "next_pane", "prev pane", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader("watchlist")
        with TabbedContent(id="watchlist-tabs"):
            with TabPane("Events", id="pane-watch-events"):
                yield EventsBrowser(id="watchlist-browser")
                yield Static(
                    "Nothing starred yet. Press space on any event to star it.",
                    classes="empty-note",
                    id="empty-events",
                )
            with TabPane("Traders", id="pane-watch-users"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="users-table")
                yield Static(
                    "No traders followed. Search (/) a name and press space on a trader.",
                    classes="empty-note",
                    id="empty-users",
                )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "watchlist"
        users = self.query_one("#users-table", VimDataTable)
        users.add_column("Trader", width=30, key="name")
        users.add_column("Address", width=16, key="address")
        users.add_column("Positions value", width=16, key="value")
        for tabs in self.query("Tabs"):
            tabs.can_focus = False
        self.load_watchlist()
        self.load_users()

    # -- events pane ----------------------------------------------------------

    @property
    def table(self) -> EventsTable:
        return self.query_one(EventsTable)

    @work(exclusive=True, group="events")
    async def load_watchlist(self) -> None:
        slugs = self.app.watchlist.slugs
        browser = self.query_one(EventsBrowser)
        note = self.query_one("#empty-events", Static)
        note.display = not slugs
        browser.display = bool(slugs)
        if not slugs:
            self.table.clear()
            self.table.events_by_slug.clear()
            return
        results = await asyncio.gather(
            *(self.app.gamma.event_by_slug(s) for s in slugs), return_exceptions=True
        )
        events = [e for e in results if e is not None and not isinstance(e, BaseException)]
        failed = len(slugs) - len(events)
        self.table.set_events(events, set(slugs))
        self.table.focus()
        browser.preview.show_event(events[0] if events else None)
        if failed:
            self.notify(f"{failed} watched event(s) could not be loaded", severity="warning")

    # -- traders pane -------------------------------------------------------------

    @work(exclusive=True, group="users")
    async def load_users(self) -> None:
        watched = self.app.watchlist.users
        table = self.query_one("#users-table", VimDataTable)
        note = self.query_one("#empty-users", Static)
        note.display = not watched
        table.display = bool(watched)
        table.clear()
        if not watched:
            return
        values = await asyncio.gather(
            *(self.app.data.portfolio_value(u["address"]) for u in watched),
            return_exceptions=True,
        )
        for user, value in zip(watched, values, strict=True):
            shown = "-" if isinstance(value, BaseException) or value is None else fmt.money(value)
            table.add_row(
                fmt.trunc(user.get("name") or user["address"], 30),
                f"{user['address'][:6]}...{user['address'][-4:]}",
                shown,
                key=user["address"],
            )

    # -- actions ---------------------------------------------------------------------

    def _active_pane(self) -> str:
        return self.query_one(TabbedContent).active

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "users-table":
            address = str(event.row_key.value)
            user = next((u for u in self.app.watchlist.users if u["address"] == address), None)
            if user is not None:
                from polymarket_tui.ui.screens.user import UserScreen

                self.app.push_screen(UserScreen(address, user.get("name") or address[:10]))
            return
        selected = self.table.highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def action_toggle_watch(self) -> None:
        if self._active_pane() == "pane-watch-users":
            table = self.query_one("#users-table", VimDataTable)
            if table.cursor_row is None or table.row_count == 0:
                return
            address = str(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
            self.app.watchlist.toggle_user(address, "")
            self.load_users()
            return
        selected = self.table.highlighted_event()
        if selected is None:
            return
        self.app.watchlist.toggle(selected.slug)
        self.load_watchlist()

    def action_next_pane(self) -> None:
        tabbed = self.query_one(TabbedContent)
        panes = ["pane-watch-events", "pane-watch-users"]
        idx = (panes.index(tabbed.active) + 1) % len(panes) if tabbed.active in panes else 0
        tabbed.active = panes[idx]
        if idx == 1 and self.app.watchlist.users:
            self.query_one("#users-table", VimDataTable).focus()
        elif idx == 0 and self.app.watchlist.slugs:
            self.table.focus()

    def action_refresh(self) -> None:
        self.load_watchlist()
        self.load_users()
