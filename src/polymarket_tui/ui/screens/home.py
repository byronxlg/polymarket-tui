"""Home: trending events with category tabs, sort cycling, and preview.

The logic lives in HomePane (a widget) so NavHost can host it as the root pane
of the 30/70 drill split.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, Tab, Tabs

from polymarket_tui.api.gamma import SORT_ORDERS
from polymarket_tui.ui.tiers import Tier, TierAware
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


class HomePane(TierAware, Vertical):
    """Trending events browser - the root pane of the drill navigation."""

    header_title = "polymarket-tui"

    BINDINGS = [
        Binding("o", "cycle_sort", "sort"),
        Binding("space", "toggle_watch", "star"),
        Binding("tab", "next_tag", "category"),
        Binding("shift+tab", "prev_tag", "prev category", show=False),
        Binding("r", "refresh", "refresh", show=False),
        Binding("enter", "open_event", "open", show=False, priority=False),
        Binding("down", "leave_tag_bar", "back to list", show=False),
        Binding("escape", "leave_tag_bar", "back to list", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tag_slug: str | None = None
        self._sort_index = 0
        self._offset = 0
        self._loading = False

    def compose(self) -> ComposeResult:
        yield Tabs(*(Tab(label, id=slug) for label, slug in CATEGORIES), id="tag-bar")
        yield Static(self._status_line(), id="status-line", classes="subtle")
        yield EventsBrowser(id="home-browser")

    def _status_line(self) -> Text:
        out = Text()
        out.append(" sort ", style="dim")
        out.append(SORT_LABELS[SORT_ORDERS[self._sort_index]], style="bold")
        out.append("   o cycle sort   tab category", style="dim")
        return out

    def on_mount(self) -> None:
        self.query_one(Tabs).can_focus = False
        self.table.apply_tier(self.tier)
        self.table.focus()
        self.load_events()
        self.tier_ready()

    def on_tier_changed(self, tier: Tier) -> None:
        self.table.apply_tier(tier)

    def focus_inner(self) -> None:
        self.table.focus()

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
        now = datetime.now(UTC)
        # Gamma still returns just-ended events as active; hide them like the
        # web trending list does (they read as noise next to live markets).
        events = [
            e
            for e in events
            if e.top_market is not None and (e.end_date is None or e.end_date > now)
        ]
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
        if self.query_one(Tabs).has_focus:
            self.action_leave_tag_bar()
            return
        self._open_highlighted()

    # -- spatial navigation: up from the top row enters the category bar --------

    def on_vim_data_table_top_reached(self, message) -> None:
        tabs = self.query_one(Tabs)
        tabs.can_focus = True
        tabs.focus()

    def action_leave_tag_bar(self) -> None:
        tabs = self.query_one(Tabs)
        if tabs.has_focus:
            tabs.can_focus = False
            self.table.focus()

    def action_cycle_sort(self) -> None:
        self._sort_index = (self._sort_index + 1) % len(SORT_ORDERS)
        self.query_one("#status-line", Static).update(self._status_line())
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
