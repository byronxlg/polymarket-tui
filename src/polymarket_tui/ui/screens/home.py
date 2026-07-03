"""Home screen: trending events with category tabs, sort cycling, and preview."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static, Tab, Tabs

from polymarket_tui.api.gamma import SORT_ORDERS
from polymarket_tui.core import fmt
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser

# Curated to match the polymarket.com top nav. id = gamma tag_slug ("trending" = no filter).
CATEGORIES: list[tuple[str, str]] = [
    ("Trending", "trending"),
    ("Politics", "politics"),
    ("Sports", "sports"),
    ("Crypto", "crypto"),
    ("Economy", "economy"),
    ("Tech", "tech"),
    ("Culture", "culture"),
    ("World", "world"),
    ("Elections", "elections"),
]

PAGE_SIZE = 50

SORT_LABELS = {
    "volume24hr": "24h volume",
    "liquidity": "liquidity",
    "endDate": "ending soonest",
    "startDate": "newest",
}


class HomeScreen(Screen):
    BINDINGS = [
        Binding("o", "cycle_sort", "sort"),
        Binding("W", "toggle_watch", "watch", key_display="W"),
        Binding("tab", "next_tag", "next category"),
        Binding("shift+tab", "prev_tag", "prev category", show=False),
        Binding("h", "prev_tag", "prev tab", show=False),
        Binding("l", "next_tag", "next tab", show=False),
        Binding("left_square_bracket", "prev_tag", "prev tag", show=False),
        Binding("right_square_bracket", "next_tag", "next tag", show=False),
        Binding("r", "refresh", "refresh"),
        Binding("enter", "open_event", "open", show=False, priority=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tag_slug: str | None = None
        self._sort_index = 0
        self._offset = 0
        self._loading = False
        self._balances = ""

    def compose(self) -> ComposeResult:
        yield AppHeader("polymarket-tui")
        yield Tabs(*(Tab(label, id=slug) for label, slug in CATEGORIES), id="tag-bar")
        yield Static(self._status_line(), id="status-line", classes="subtle")
        yield EventsBrowser(id="home-browser")
        yield Footer()

    def _status_line(self, balances: str = "") -> str:
        line = f" sort: {SORT_LABELS[SORT_ORDERS[self._sort_index]]}  (o to cycle, tab category)"
        mode = self.app.settings.mode.value
        line += f"  |  {mode}"
        if balances:
            line += f"  |  {balances}"
        return line

    def on_mount(self) -> None:
        self.title = "polymarket-tui"
        self.query_one(Tabs).can_focus = False
        self.table.focus()
        self.load_events()
        self.load_balances()

    @work(exclusive=True, group="balances")
    async def load_balances(self) -> None:
        app = self.app
        parts = []
        try:
            balance = await app.portfolio.usdc_balance()
            if balance is not None:
                parts.append(f"cash {fmt.money(balance)}")
            value = await app.portfolio.portfolio_value()
            if value is not None:
                parts.append(f"positions {fmt.money(value)}")
        except Exception:
            return
        self._balances = "  ".join(parts)
        self.query_one("#status-line", Static).update(self._status_line(self._balances))

    def on_screen_resume(self) -> None:
        # Credentials may have changed on the auth screen - refresh mode/balances.
        self.query_one("#status-line", Static).update(self._status_line(self._balances))
        self.load_balances()

    @property
    def table(self) -> EventsTable:
        return self.query_one(EventsTable)

    @work(exclusive=True)
    async def load_events(self, append: bool = False) -> None:
        app = self.app
        self._loading = True
        if not append:
            self._offset = 0
        order = SORT_ORDERS[self._sort_index]
        ascending = order == "endDate"
        try:
            events = await app.gamma.events(
                limit=PAGE_SIZE,
                offset=self._offset,
                order=order,
                ascending=ascending,
                tag_slug=self._tag_slug,
            )
        except Exception as exc:
            self.notify(f"Failed to load events: {exc}", severity="error", timeout=6)
            self._loading = False
            return
        events = [e for e in events if e.top_market is not None]
        self.table.set_events(events, set(app.watchlist.slugs), clear=not append)
        if not append:
            browser = self.query_one(EventsBrowser)
            browser.preview.show_event(events[0] if events else None)
        self._loading = False

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        slug = event.tab.id
        self._tag_slug = None if slug == "trending" else slug
        self.load_events()

    def on_data_table_row_selected(self, event) -> None:
        self._open_highlighted()

    def on_data_table_row_highlighted(self, event) -> None:
        # Infinite scroll: fetch the next page when the cursor nears the bottom.
        if (
            not self._loading
            and self.table.row_count >= PAGE_SIZE
            and event.cursor_row is not None
            and event.cursor_row >= self.table.row_count - 5
        ):
            self._offset += PAGE_SIZE
            self.load_events(append=True)

    def _open_highlighted(self) -> None:
        event = self.table.highlighted_event()
        if event is not None:
            self.app.open_event(event)

    def action_open_event(self) -> None:
        self._open_highlighted()

    def action_cycle_sort(self) -> None:
        self._sort_index = (self._sort_index + 1) % len(SORT_ORDERS)
        self.query_one("#status-line", Static).update(self._status_line(self._balances))
        self.load_events()

    def action_toggle_watch(self) -> None:
        event = self.table.highlighted_event()
        if event is None:
            return
        watched = self.app.watchlist.toggle(event.slug)
        self.table.set_star(event.slug, watched)
        self.notify(("Watching " if watched else "Unwatched ") + event.title[:40], timeout=2)

    def action_refresh(self) -> None:
        self.load_events()

    def _move_tag(self, delta: int) -> None:
        tabs = self.query_one(Tabs)
        if delta > 0:
            tabs.action_next_tab()
        else:
            tabs.action_previous_tab()

    def action_prev_tag(self) -> None:
        self._move_tag(-1)

    def action_next_tag(self) -> None:
        self._move_tag(1)
