"""Holdings/order flags must survive a clear=True reload (regression:
the cursor-restore local shadowed the `held` parameter and corrupted it)."""

from __future__ import annotations

from textual.app import App, ComposeResult

from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.event_table import EventsTable

EVENTS = [Event(slug=f"ev-{i}", title=f"Event number {i}") for i in range(4)]


class Host(App):
    def compose(self) -> ComposeResult:
        yield EventsTable()


async def test_held_flags_survive_reload() -> None:
    app = Host()
    async with app.run_test(size=(120, 30)):
        table = app.query_one(EventsTable)
        table.set_events(EVENTS, watched=set(), clear=True, held={"ev-1"})
        assert table._held == {"ev-1"}
        table.move_cursor(row=2)
        table.set_events(EVENTS, watched=set(), clear=True, held={"ev-1", "ev-3"})
        assert table._held == {"ev-1", "ev-3"}
