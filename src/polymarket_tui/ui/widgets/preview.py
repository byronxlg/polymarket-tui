"""Events browser: table plus a preview panel for the highlighted/hovered event."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal, VerticalScroll
from textual.events import MouseMove
from textual.widgets import DataTable, Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.event_table import EventsTable

PREVIEW_OUTCOMES = 12


class EventPreview(Static):
    def show_event(self, event: Event | None) -> None:
        if event is None:
            self.update(Text("", style="dim"))
            return
        out = Text()
        out.append(event.title.strip() + "\n", style="bold")
        meta = []
        if event.end_date:
            meta.append(f"ends {fmt.end_date(event.end_date)}")
        if event.volume_24hr:
            meta.append(f"vol24h {fmt.money(event.volume_24hr)}")
        if event.liquidity:
            meta.append(f"liq {fmt.money(event.liquidity)}")
        if meta:
            out.append("  ".join(meta) + "\n", style="dim")
        out.append("\n")

        markets = event.active_markets
        for market in markets[:PREVIEW_OUTCOMES]:
            price = market.yes_price
            out.append(f"{market.display_title[:26]:<27}", style="")
            out.append(f"{fmt.cents(price):>7}", style="bold cyan")
            change = market.one_day_price_change
            if change:
                style = "green" if change > 0 else "red"
                out.append(f" {fmt.cents(change, signed=True):>7}", style=style)
            out.append("\n")
        if len(markets) > PREVIEW_OUTCOMES:
            out.append(f"... {len(markets) - PREVIEW_OUTCOMES} more\n", style="dim")

        if event.description:
            out.append("\n")
            desc = event.description.strip().replace("\n", " ")
            out.append(desc[:280] + ("..." if len(desc) > 280 else ""), style="dim")
        self.update(out)


class EventsBrowser(Horizontal):
    """EventsTable with a side preview that follows the cursor and mouse hover."""

    def compose(self):
        yield EventsTable(id="events-table")
        with VerticalScroll(id="preview-pane"):
            yield EventPreview(id="event-preview")

    @property
    def table(self) -> EventsTable:
        return self.query_one(EventsTable)

    @property
    def preview(self) -> EventPreview:
        return self.query_one(EventPreview)

    def _preview_slug(self, slug: str | None) -> None:
        if slug:
            self.preview.show_event(self.table.events_by_slug.get(slug))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            self._preview_slug(str(event.row_key.value))

    def on_mouse_move(self, event: MouseMove) -> None:
        hover_row = self.table.hover_row
        if hover_row is not None and 0 <= hover_row < self.table.row_count:
            try:
                key = self.table.coordinate_to_cell_key((hover_row, 0)).row_key
            except Exception:
                return
            self._preview_slug(str(key.value))
