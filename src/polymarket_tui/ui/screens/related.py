"""Related markets: series siblings (recurring markets like dailies) or same-tag events.

A pop-out over the current pane (Byron, 2026-07-06): related is a
transient lookup, not a navigation level - glance at the siblings, star
one, or open one (which closes the pop-out and drills to it); esc drops
back to exactly where you were, trail untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.order_details import action_hints
from polymarket_tui.ui.widgets.preview import EventsBrowser


class RelatedModal(ModalScreen[None]):
    """Series-sibling / same-tag events in a pop-out."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "close"),
        Binding("space", "toggle_watch", "star"),
        # Modal screens cut the binding chain, so the app's global R can't
        # reach us - rebind it locally to keep refresh-anywhere true.
        Binding("R", "refresh", "refresh", show=False, key_display="R"),
    ]

    DEFAULT_CSS = """
    RelatedModal {
        align: center middle;
        background: $background 40%;
    }
    RelatedModal > Vertical {
        width: 80%;
        max-width: 160;
        height: 80%;
        border: round $primary;
        background: $surface;
        padding: 0 1 0 1;
    }
    RelatedModal #related-hints {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self, event: Event) -> None:
        super().__init__()
        self._event = event

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title_line(), classes="screen-title")
            yield EventsBrowser(id="related-browser")
            yield Static(
                action_hints(("space", "star"), ("esc", "close")), id="related-hints"
            )

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
        self.table.focus()
        self.load_related()

    @property
    def table(self) -> EventsTable:
        return self.query_one(EventsTable)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @work(exclusive=True)
    async def load_related(self) -> None:
        app = self.app
        series = self._event.primary_series
        try:
            if series is not None:
                events = await app.gamma.events_by_series(series.id)
                # Soonest-resolving open events first, then the recent past.
                # The key must not mix datetime and str (TypeError kills the
                # whole pop-out) - dateless events sort last, by slug.
                far_future = datetime.max.replace(tzinfo=UTC)
                open_events = sorted(
                    (e for e in events if not e.closed),
                    key=lambda e: (e.end_date or far_future, e.slug),
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
        if not self.is_mounted:
            return  # dismissed while the lookup was in flight
        events = [e for e in events if e.slug != self._event.slug]
        self.table.set_events(events, set(app.watchlist.slugs))
        browser = self.query_one(EventsBrowser)
        browser.preview.show_event(events[0] if events else None)

    def on_data_table_row_selected(self, event) -> None:
        # open_event pops overlay screens (this modal included) before it
        # drills, so selecting a sibling closes the pop-out and opens it.
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
        """The global R reloads the pop-out's list in place."""
        self.load_related()
