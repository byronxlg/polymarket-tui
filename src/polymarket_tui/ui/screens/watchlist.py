"""Watchlist: starred events and followed traders.

Logic lives in WatchlistPane so NavHost can host it as an alternate ROOT of
the drill navigation ('w') - the same top level as Home. Opening a starred
event drills it as the 70% child with the watchlist kept as the 30% parent;
left/esc from the watchlist root returns to Home.
"""

from __future__ import annotations

import asyncio

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane

from polymarket_tui.core import fmt
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.tiers import Tier, TierAware, effective_tier
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser
from polymarket_tui.ui.widgets.vim_table import VimDataTable

# (key, label, width) per width tier for the followed-traders table.
USERS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("name", "Trader", 30),
        ("address", "Address", 16),
        ("value", "Positions value", 16),
    ),
    "medium": (
        ("name", "Trader", 30),
        ("address", "Address", 16),
        ("value", "Positions value", 16),
    ),
    "compact": (
        ("name", "Trader", 26),
        ("value", "Value", 12),
    ),
}


class WatchlistPane(TierAware, Vertical):
    """Starred events + followed traders - an alternate root drill pane."""

    header_title = "watchlist"
    # An emptied tab hides its table; the pane itself takes focus then so
    # tab/esc keep dispatching (bindings need focus inside the pane).
    can_focus = True

    BINDINGS = [
        Binding("escape", "app.nav_back", "back", show=False),
        Binding("space", "toggle_watch", "unwatch"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "next_pane", "prev pane", show=False),
        Binding("b", "order('BUY')", "buy", show=False),
        Binding("s", "order('SELL')", "sell", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Rendered rows kept for tier re-renders; loaded sets for staleness
        # checks when focus returns from a drill child.
        self._users_rows: list[tuple[str, str, str]] = []  # (name, address, value)
        self._users_tier: Tier = "full"
        self._loaded_slugs: set[str] = set()
        self._loaded_users: set[str] = set()

    def compose(self) -> ComposeResult:
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

    def on_mount(self) -> None:
        self._users_tier = self.tier
        self._build_users_columns()
        for tabs in self.query("Tabs"):
            tabs.can_focus = False
        self.table.apply_tier(self.tier)
        self.load_watchlist()
        self.load_users()
        self.tier_ready()
        self._schedule_refit()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """An empty tab has nothing to unwatch - don't advertise space (the
        empty-note is telling the user to go star things instead)."""
        if action == "toggle_watch" and self.is_mounted:
            if self._active_pane() == "pane-watch-users":
                table = next(iter(self.query("#users-table")), None)
            else:
                table = next(iter(self.query(EventsTable)), None)
            return table is not None and table.row_count > 0
        return True

    def focus_inner(self) -> None:
        if self._active_pane() == "pane-watch-users":
            table = self.query_one("#users-table", VimDataTable)
        else:
            table = self.table
        # A hidden (emptied) table cannot take focus - the pane does instead.
        if table.display:
            table.focus()
        else:
            self.focus()
        # Stars/follows may have changed while a drill child had focus.
        if set(self.app.watchlist.slugs) != self._loaded_slugs:
            self.load_watchlist()
        if {u["address"] for u in self.app.watchlist.users} != self._loaded_users:
            self.load_users()

    def _reclaim_focus(self) -> None:
        """A just-emptied tab hid the focused table - keep focus in the pane
        so tab (next pane) and esc keep working; never steal it from a
        drill child that legitimately has it. Deferred: Textual blurs the
        hidden table only on the next refresh, so deciding now would read
        stale focus (and the footer would keep the stale hints)."""

        def _later() -> None:
            if not alive(self):
                return
            focused = self.app.focused
            if focused is None or self in focused.ancestors_with_self:
                self.focus_inner()
            self.refresh_bindings()

        self.call_after_refresh(_later)

    # -- width tiers ----------------------------------------------------------

    def _build_users_columns(self) -> None:
        table = self.query_one("#users-table", VimDataTable)
        table.clear(columns=True)
        for key, label, width in USERS_TIER_COLUMNS[self._users_tier]:
            table.add_column(label, width=width, key=key)

    def on_tier_changed(self, tier: Tier) -> None:
        self.table.apply_tier(tier)
        self._schedule_refit()

    def on_resize(self) -> None:
        if self._tier_ready:
            self._schedule_refit()

    def _schedule_refit(self) -> None:
        self.call_after_refresh(self._refit_users)

    def _refit_users(self) -> None:
        if not alive(self):
            return  # call_after_refresh can fire after the pane is torn down
        width = self.size.width - 2
        if width <= 0:
            return
        tier = effective_tier(self.tier, width, USERS_TIER_COLUMNS)
        if tier == self._users_tier:
            return
        self._users_tier = tier
        self._build_users_columns()
        self._render_users()

    # -- events pane ----------------------------------------------------------

    @property
    def table(self) -> EventsTable:
        return self.query_one(EventsTable)

    def action_order(self, side: str) -> None:
        if not self.table.has_focus:
            return  # traders pane active
        event = self.table.highlighted_event()
        if event is not None:
            self.app.quick_order(event, side)

    @work(exclusive=True, group="events")
    async def load_watchlist(self) -> None:
        slugs = self.app.watchlist.slugs
        self._loaded_slugs = set(slugs)
        browser = self.query_one(EventsBrowser)
        note = self.query_one("#empty-events", Static)
        note.display = not slugs
        browser.display = bool(slugs)
        if not slugs:
            self.table.clear()
            self.table.events_by_slug.clear()
            self._reclaim_focus()
            self.refresh_bindings()  # space gates on row_count (check_action)
            return
        results = await asyncio.gather(
            *(self.app.gamma.event_by_slug(s) for s in slugs), return_exceptions=True
        )
        if not alive(self):
            return  # pane torn down while we fetched
        events = [e for e in results if e is not None and not isinstance(e, BaseException)]
        failed = len(slugs) - len(events)
        self.table.set_events(events, set(slugs))
        browser.preview.show_event(events[0] if events else None)
        self.refresh_bindings()
        if failed:
            self.notify(f"{failed} watched event(s) could not be loaded", severity="warning")

    # -- traders pane -------------------------------------------------------------

    @work(exclusive=True, group="users")
    async def load_users(self) -> None:
        watched = self.app.watchlist.users
        self._loaded_users = {u["address"] for u in watched}
        table = self.query_one("#users-table", VimDataTable)
        note = self.query_one("#empty-users", Static)
        note.display = not watched
        table.display = bool(watched)
        self._users_rows = []
        if not watched:
            table.clear()
            self._reclaim_focus()
            self.refresh_bindings()  # space gates on row_count (check_action)
            return
        values = await asyncio.gather(
            *(self.app.data.portfolio_value(u["address"]) for u in watched),
            return_exceptions=True,
        )
        if not alive(self):
            return  # pane torn down while we fetched
        for user, value in zip(watched, values, strict=True):
            shown = "-" if isinstance(value, BaseException) or value is None else fmt.money(value)
            self._users_rows.append((user.get("name") or user["address"], user["address"], shown))
        self._render_users()
        self.refresh_bindings()

    def _render_users(self) -> None:
        table = self.query_one("#users-table", VimDataTable)
        table.clear()
        columns = USERS_TIER_COLUMNS[self._users_tier]
        name_w = dict((k, w) for k, _, w in columns)["name"]
        for name, address, value in self._users_rows:
            cells = {
                "name": fmt.trunc(name, name_w),
                "address": f"{address[:6]}...{address[-4:]}",
                "value": value,
            }
            table.add_row(*(cells[key] for key, _, _ in columns), key=address)

    # -- actions ---------------------------------------------------------------------

    def _active_pane(self) -> str:
        return self.query_one(TabbedContent).active

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "users-table":
            address = str(event.row_key.value)
            user = next((u for u in self.app.watchlist.users if u["address"] == address), None)
            if user is not None:
                self.app.open_user(address, user.get("name") or address[:10])
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
        self.refresh_bindings()  # the space gate follows the active tab

    def action_refresh(self) -> None:
        self.load_watchlist()
        self.load_users()
