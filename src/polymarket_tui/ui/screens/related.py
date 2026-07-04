"""Related markets: series siblings (recurring markets like dailies) or same-tag events.

Hosted as a drill pane by NavHost (30/70 split).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from polymarket_tui.models.market import Event
from polymarket_tui.ui.tiers import Tier, TierAware
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser


class RelatedPane(TierAware, Vertical):
    """Series-sibling / same-tag events - a drill pane."""

    header_title = "related"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "toggle_watch", "star"),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, event: Event, **kwargs) -> None:
        super().__init__(**kwargs)
        self._event = event

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title")
        yield EventsBrowser(id="related-browser")

    def focus_inner(self) -> None:
        self.query_one(EventsTable).focus()

    def _title_line(self) -> str:
        series = self._event.primary_series
        if series is not None:
            recurrence = f" ({series.recurrence})" if series.recurrence else ""
            return f"RELATED - {series.title}{recurrence}"
        tag = self._event.most_specific_tag
        if tag is not None:
            return f"RELATED - {tag.label}"
        return "RELATED"

    def on_mount(self) -> None:
        self.table.apply_tier(self.tier)
        self.table.focus()
        self.load_related()
        self.tier_ready()

    def on_tier_changed(self, tier: Tier) -> None:
        self.table.apply_tier(tier)

    @property
    def table(self) -> EventsTable:
        return self.query_one(EventsTable)

    @work(exclusive=True)
    async def load_related(self) -> None:
        app = self.app
        series = self._event.primary_series
        try:
            if series is not None:
                events = await app.gamma.events_by_series(series.id)
                # Soonest-resolving open events first, then the recent past.
                open_events = sorted(
                    (e for e in events if not e.closed),
                    key=lambda e: e.end_date or e.slug,
                )
                closed_events = [e for e in events if e.closed]
                events = open_events + closed_events
            else:
                tag = self._event.most_specific_tag
                if tag is None:
                    self.notify("No series or tag to relate by", severity="warning")
                    return
                events = await app.gamma.events(limit=30, tag_slug=tag.slug)
        except Exception as exc:
            self.notify(f"Related lookup failed: {exc}", severity="error")
            return
        events = [e for e in events if e.slug != self._event.slug]
        self.table.set_events(events, set(app.watchlist.slugs))
        browser = self.query_one(EventsBrowser)
        browser.preview.show_event(events[0] if events else None)

    def on_data_table_row_selected(self, event) -> None:
        selected = self.table.highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def action_toggle_watch(self) -> None:
        selected = self.table.highlighted_event()
        if selected is None:
            return
        watched = self.app.watchlist.toggle(selected.slug)
        self.table.set_star(selected.slug, watched)

    def action_refresh(self) -> None:
        self.load_related()
