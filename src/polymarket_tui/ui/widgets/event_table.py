"""Shared events table used by Home, Watchlist, and Search screens."""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.vim_table import VimDataTable


def change_text(change: float | None) -> Text:
    if change is None:
        return Text("-", style="dim")
    style = "green" if change > 0 else "red" if change < 0 else "dim"
    return Text(fmt.cents(change, signed=True), style=style)


class EventsTable(VimDataTable):
    """DataTable keyed by event slug; keeps the Event objects for row lookups."""

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.events_by_slug: dict[str, Event] = {}

    def on_mount(self) -> None:
        self.add_column(" ", width=1, key="star")
        self.add_column("Event", width=46, key="event")
        self.add_column("Top outcome", width=24, key="outcome")
        self.add_column("Price", width=7, key="price")
        self.add_column("24h", width=7, key="change")
        self.add_column("Vol 24h", width=9, key="vol")
        self.add_column("Ends", width=8, key="ends")

    def set_events(self, events: list[Event], watched: set[str], clear: bool = True) -> None:
        if clear:
            self.clear()
            self.events_by_slug.clear()
        for event in events:
            if event.slug in self.events_by_slug:
                continue
            self.events_by_slug[event.slug] = event
            top = event.top_market
            outcome = ""
            price: Text | str = ""
            if top is not None:
                outcome = top.display_title if not event.is_binary else "Yes"
                price = Text(fmt.cents(top.yes_price), style="bold cyan")
            ends = fmt.end_date(event.end_date)
            self.add_row(
                Text("*", style="yellow") if event.slug in watched else " ",
                fmt.trunc(event.title, 46),
                fmt.trunc(outcome, 24),
                price,
                change_text(top.one_day_price_change if top else None),
                fmt.money(event.volume_24hr),
                Text(ends, style="dim red") if ends == "ended" else ends,
                key=event.slug,
            )

    def highlighted_event(self) -> Event | None:
        if self.cursor_row is None or self.row_count == 0:
            return None
        row_key = self.coordinate_to_cell_key((self.cursor_row, 0)).row_key
        return self.events_by_slug.get(str(row_key.value))

    def set_star(self, slug: str, watched: bool) -> None:
        if slug in self.events_by_slug:
            self.update_cell(slug, "star", Text("*", style="yellow") if watched else " ")
