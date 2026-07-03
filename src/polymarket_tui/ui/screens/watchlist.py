"""Watchlist screen: persisted event slugs, fetched fresh on open."""

from __future__ import annotations

import asyncio

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from polymarket_tui.ui.widgets.event_table import EventsTable


class WatchlistScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("W", "toggle_watch", "unwatch", key_display="W"),
        Binding("r", "refresh", "refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("WATCHLIST", classes="screen-title")
        yield EventsTable(id="watchlist-table")
        yield Static(
            "Nothing watched yet. Press W on any event to add it.",
            classes="empty-note",
            id="empty-note",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "watchlist"
        self.load_watchlist()

    @work(exclusive=True)
    async def load_watchlist(self) -> None:
        slugs = self.app.watchlist.slugs
        table = self.query_one(EventsTable)
        note = self.query_one("#empty-note", Static)
        note.display = not slugs
        table.display = bool(slugs)
        if not slugs:
            table.clear()
            table.events_by_slug.clear()
            return
        results = await asyncio.gather(
            *(self.app.gamma.event_by_slug(s) for s in slugs), return_exceptions=True
        )
        events = [e for e in results if e is not None and not isinstance(e, BaseException)]
        failed = len(slugs) - len(events)
        table.set_events(events, set(slugs))
        table.focus()
        if failed:
            self.notify(f"{failed} watched event(s) could not be loaded", severity="warning")

    def on_data_table_row_selected(self, event) -> None:
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def action_toggle_watch(self) -> None:
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is None:
            return
        self.app.watchlist.toggle(selected.slug)
        self.load_watchlist()

    def action_refresh(self) -> None:
        self.load_watchlist()
