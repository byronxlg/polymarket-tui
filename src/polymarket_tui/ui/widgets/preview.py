"""Events browser: table plus a preview panel for the highlighted/hovered event."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal, VerticalScroll
from textual.events import MouseMove
from textual.widgets import DataTable, Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.widgets.event_table import EventsTable

PREVIEW_OUTCOMES = 18


class MarketPreview(Static):
    """Detail rail for one outcome market (used on the event screen)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._market: Market | None = None

    def on_resize(self) -> None:
        # Truncation widths follow the rendered width - re-render on change.
        self.show_market(self._market)

    def show_market(self, market: Market | None) -> None:
        self._market = market
        if market is None:
            self.update(Text("", style="dim"))
            return
        w = max(20, self.size.width or 44)
        out = Text()
        out.append(fmt.trunc(market.display_title, w) + "\n", style="bold")
        if market.question and market.question != market.display_title:
            # Full question - the panel wraps and scrolls, no need to cut it.
            out.append(market.question.strip() + "\n", style="dim")
        out.append("\n")
        out.append(f"{'YES':<8}", style="bold green")
        out.append(f"{fmt.cents(market.yes_price):>8}\n", style="bold cyan")
        no_price = None if market.yes_price is None else 1 - market.yes_price
        out.append(f"{'NO':<8}", style="bold red")
        out.append(f"{fmt.cents(no_price):>8}\n\n", style="bold cyan")

        rows = [
            ("bid", fmt.cents(market.best_bid)),
            ("ask", fmt.cents(market.best_ask)),
            ("spread", fmt.cents(market.spread)),
            (
                "24h",
                fmt.cents(market.one_day_price_change, signed=True)
                if market.one_day_price_change is not None
                else "-",
            ),
            ("vol 24h", fmt.money(market.volume_24hr)),
            ("liquidity", fmt.money(market.liquidity)),
            ("ends", fmt.end_date(market.end_date)),
        ]
        if market.order_price_min_tick_size:
            rows.append(("tick", f"{market.order_price_min_tick_size}"))
        if market.order_min_size:
            rows.append(("min size", f"{market.order_min_size:.0f}"))
        for label, value in rows:
            out.append(f"{label:<10}", style="dim")
            out.append(f"{value}\n")
        self.update(out)


class EventPreview(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._event: Event | None = None

    def on_resize(self) -> None:
        # Truncation widths follow the rendered width - re-render on change.
        self.show_event(self._event)

    def show_event(self, event: Event | None) -> None:
        self._event = event
        if event is None:
            self.update(Text("", style="dim"))
            return
        w = max(20, self.size.width or 44)
        # Outcome rows: the name column fills what price (7) + change (8) leave.
        name_w = max(12, w - 16)
        out = Text()
        out.append(fmt.trunc(event.title, w) + "\n", style="bold")
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
            out.append(f"{fmt.trunc(market.display_title, name_w):<{name_w + 1}}", style="")
            out.append(f"{fmt.cents(price):>7}", style="bold cyan")
            change = market.one_day_price_change
            if change:
                style = "green" if change > 0 else "red"
                out.append(f" {fmt.cents(change, signed=True):>7}", style=style)
            out.append("\n")
        if len(markets) > PREVIEW_OUTCOMES:
            out.append(f"... {len(markets) - PREVIEW_OUTCOMES} more\n", style="dim")

        if event.description:
            # Full description - the panel wraps and scrolls, no need to cut it.
            out.append("\n")
            out.append(event.description.strip().replace("\n", " "), style="dim")
        self.update(out)


class EventsBrowser(Horizontal):
    """EventsTable with a side preview that follows the cursor and mouse hover."""

    def compose(self):
        yield EventsTable(id="events-table")
        pane = VerticalScroll(EventPreview(id="event-preview"), id="preview-pane")
        pane.can_focus = False
        yield pane

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
