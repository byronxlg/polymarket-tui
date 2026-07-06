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
from polymarket_tui.state import cache
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.theme import AMBER
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

PAGE_SIZE = 100  # Gamma's per-request ceiling; one page fills any terminal

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
        Binding("o", "cycle_sort", "sort", show=False),
        Binding("space", "toggle_watch", "star"),
        Binding("tab", "next_tag", "category"),
        Binding("shift+tab", "prev_tag", "prev category", show=False),
        Binding("b", "order('BUY')", "buy"),
        Binding("s", "order('SELL')", "sell"),
        Binding("W", "app.watchlist", "watched", key_display="W"),
        Binding("enter", "open_event", "open", show=False, priority=False),
        Binding("down", "leave_tag_bar", "back to list", show=False),
        Binding("escape", "app.nav_back", "back", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tag_slug: str | None = None
        self._sort_index = 0
        self._offset = 0
        self._loading = False
        self._load_gen = 0
        self._exhausted = False  # Gamma returned a short page: no more to fetch

    def compose(self) -> ComposeResult:
        yield Tabs(*(Tab(label, id=slug) for label, slug in CATEGORIES), id="tag-bar")
        yield Static(self._status_line(), id="status-line", classes="subtle")
        yield EventsBrowser(id="home-browser")

    def _status_line(self) -> Text:
        out = Text(justify="center")
        out.append("sort ", style="dim")
        out.append(SORT_LABELS[SORT_ORDERS[self._sort_index]], style="bold")
        out.append("  \u00b7  o cycle sort  \u00b7  tab category", style="dim")
        return out

    def on_mount(self) -> None:
        self.query_one(Tabs).can_focus = False
        self.table.apply_tier(self.tier)
        self.table.focus()
        self._show_cached()
        self.load_events()
        self.tier_ready()

    def _cache_key(self) -> str:
        return f"home:{self._tag_slug or 'trending'}:{SORT_ORDERS[self._sort_index]}"

    def _show_cached(self) -> None:
        """Last session's list, instantly - the live fetch replaces it."""
        events = cache.load_events(self._cache_key())
        if not events:
            # First run (no cache): the table is empty for however long the
            # Gamma fetch takes - say so instead of sitting silent.
            status = Text(justify="center")
            status.append("fetching live markets...", style="dim")
            self.query_one("#status-line", Static).update(status)
            return
        self.table.set_events(events, set(self.app.watchlist.slugs), clear=True)
        browser = self.query_one(EventsBrowser)
        browser.preview.show_event(events[0] if events else None)
        status = Text()
        status.append(" cached list from your last session ", style=AMBER)
        status.append(" refreshing...", style="dim")
        self.query_one("#status-line", Static).update(status)

    def action_order(self, side: str) -> None:
        event = self.table.highlighted_event()
        if event is not None:
            self.app.quick_order(event, side)

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
        # Generation guard: exclusive cancellation runs a superseded worker's
        # finally AFTER the replacement set _loading - only the newest run may
        # clear the flag, or the scroll trigger reopens mid-flight.
        self._load_gen += 1
        gen = self._load_gen
        try:
            if not append:
                self._offset = 0
                self._exhausted = False
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
                if alive(self):
                    self.notify(f"Failed to load events: {exc}", severity="error", timeout=6)
                    self.query_one("#status-line", Static).update(self._status_line())
                return
            # Advance past the page just fetched; a short page means the end.
            # Both track the RAW count - the ended-events filter below shrinks
            # pages, and judging by filtered size would stop pagination early.
            self._offset += PAGE_SIZE
            if len(events) < PAGE_SIZE:
                self._exhausted = True
            now = datetime.now(UTC)
            # Gamma still returns just-ended events as active; hide them like the
            # web trending list does (they read as noise next to live markets).
            events = [
                e
                for e in events
                if e.top_market is not None and (e.end_date is None or e.end_date > now)
            ]
            ordered, held = await app.portfolio.flag_slugs(events)
            if not alive(self):
                return  # the pane was torn down (root swap) while we fetched
            self.table.set_events(
                events, set(app.watchlist.slugs), clear=not append, ordered=ordered, held=held
            )
            if not append:
                browser = self.query_one(EventsBrowser)
                # Follow the (possibly restored) cursor, not row 0 - a reload
                # keeps the cursor on its event, so the preview must match.
                browser.preview.show_event(
                    self.table.highlighted_event() or (events[0] if events else None)
                )
                cache.save_events(self._cache_key(), events)
                self.query_one("#status-line", Static).update(self._status_line())
        finally:
            if gen == self._load_gen:
                self._loading = False

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        slug = event.tab.id
        self._tag_slug = None if slug == "trending" else slug
        self.load_events()

    def on_data_table_row_selected(self, event) -> None:
        self._open_highlighted()

    def on_data_table_row_highlighted(self, event) -> None:
        # Infinite scroll: fetch the next page when the cursor nears the
        # bottom. No row-count floor: the ended-events filter shrinks pages,
        # so a full table can hold fewer than PAGE_SIZE rows - _exhausted
        # (not size) says whether Gamma has more.
        if (
            not self._loading
            and not self._exhausted
            and self.table.row_count > 0
            and event.cursor_row is not None
            and event.cursor_row >= self.table.row_count - 5
        ):
            # Claim the guard NOW: @work only sets it when the worker starts,
            # and key-repeat fires more highlights before that - each used to
            # schedule a new exclusive fetch cancelling the last (profiled:
            # this guard plus the follow throttles cut worker spawns from 96
            # to 40 over one identical scroll-hammer session).
            self._loading = True
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

    def handle_back(self) -> bool:
        """esc steps out of the tag bar first; otherwise NavHost handles it
        (collapse the split / no-op at the root), same as every other pane."""
        if self.query_one(Tabs).has_focus:
            self.action_leave_tag_bar()
            return True
        return False

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
        if watched:
            # Say where starred things live - w is invisible otherwise.
            self.notify(f"Watching {event.title[:40]} - w opens your watchlist", timeout=3)
        else:
            self.notify("Unwatched " + event.title[:40], timeout=2)

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
