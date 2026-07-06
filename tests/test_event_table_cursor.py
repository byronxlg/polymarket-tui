"""Reloads must not snap the events-list cursor to the top.

set_events(clear=True) runs on the boot cache->live swap and on r refresh;
the cursor follows the highlighted event by slug when it survives the
reload, and only resets when the event is gone (e.g. a category switch).
"""

from __future__ import annotations

from textual.app import App, ComposeResult

from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.event_table import EventsTable

EVENTS = [Event(slug=f"ev-{i}", title=f"Event number {i}") for i in range(8)]


class Host(App):
    def compose(self) -> ComposeResult:
        yield EventsTable()


async def test_reload_keeps_cursor_on_the_same_event() -> None:
    app = Host()
    async with app.run_test(size=(120, 30)):
        table = app.query_one(EventsTable)
        table.set_events(EVENTS, watched=set(), clear=True)
        table.move_cursor(row=5)
        assert table.highlighted_event().slug == "ev-5"
        # Reload with the same list reordered: the cursor follows ev-5.
        table.set_events(list(reversed(EVENTS)), watched=set(), clear=True)
        assert table.highlighted_event().slug == "ev-5"
        assert table.cursor_row == 2


async def test_reload_resets_cursor_when_event_is_gone() -> None:
    app = Host()
    async with app.run_test(size=(120, 30)):
        table = app.query_one(EventsTable)
        table.set_events(EVENTS, watched=set(), clear=True)
        table.move_cursor(row=5)
        table.set_events(EVENTS[:3], watched=set(), clear=True)
        assert table.cursor_row == 0


async def test_append_does_not_move_cursor() -> None:
    app = Host()
    async with app.run_test(size=(120, 30)):
        table = app.query_one(EventsTable)
        table.set_events(EVENTS[:4], watched=set(), clear=True)
        table.move_cursor(row=2)
        table.set_events(EVENTS[4:], watched=set(), clear=False)
        assert table.highlighted_event().slug == "ev-2"
        assert table.row_count == 8


class _SpaciousBootHost(App):
    """Boot at spacious density: the cached list paints the instant the table
    mounts, ahead of the first resize refit (the crash window in issue)."""

    def __init__(self) -> None:
        super().__init__()
        self.density = "spacious"

    def compose(self) -> ComposeResult:
        yield _BootTable()


class _BootTable(EventsTable):
    def on_mount(self) -> None:
        super().on_mount()
        # Mirror the home screen painting the boot cache during mount.
        self.set_events(EVENTS, watched=set(), clear=True)


async def test_spacious_boot_cache_render_does_not_crash() -> None:
    # Rendering spacious rows (which omit change/vol) against a stale condensed
    # column spec raised KeyError: 'change'. on_mount now seeds the density's
    # spec first, so the boot render (fired from _BootTable.on_mount) and the
    # column set agree - reaching this line means mount did not raise.
    app = _SpaciousBootHost()
    async with app.run_test(size=(120, 30)):
        table = app.query_one(EventsTable)
        # Re-drive now that the table is laid out, and confirm the columns are
        # the spacious set (no change/vol) that spacious rows render against.
        table.set_events(EVENTS, watched=set(), clear=True)
        assert table.row_count == len(EVENTS)
        assert {c.value for c in table.columns}.isdisjoint({"change", "vol"})
