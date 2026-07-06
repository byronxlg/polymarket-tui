"""Events browser: table plus a preview panel for the highlighted/hovered event."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal, VerticalScroll
from textual.events import MouseMove
from textual.widgets import DataTable, Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.follow import CursorFollow
from polymarket_tui.ui.theme import BLUE, DOWN, TRACK, UP
from polymarket_tui.ui.widgets.event_table import EventsTable

PREVIEW_OUTCOMES = 18
BAR_W = 8


def prob_bar(price: float | None, width: int = BAR_W) -> Text:
    """Small probability bar: filled cells proportional to price (0-1)."""
    out = Text()
    if price is None:
        return out.append(" " * width)
    filled = round(max(0.0, min(1.0, price)) * width)
    out.append("\u2588" * filled, style=BLUE)
    out.append("\u00b7" * (width - filled), style=TRACK)
    return out


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
        out = Text()
        out.append(market.display_title + "\n", style="bold")
        if market.question and market.question != market.display_title:
            # Full question - the panel wraps and scrolls, no need to cut it.
            out.append(market.question.strip() + "\n", style="dim")
        out.append("\n")
        no_price = None if market.yes_price is None else 1 - market.yes_price
        yes_no = (("YES", f"bold {UP}", market.yes_price), ("NO", f"bold {DOWN}", no_price))
        for label, style, price in yes_no:
            out.append(f"{label:<5}", style=style)
            out.append_text(prob_bar(price))
            out.append(f"{fmt.cents(price):>8}\n", style="bold")
        out.append("\n")

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
            ("vol 24h", fmt.vol(market.volume_24hr)),
            ("liquidity", fmt.vol(market.liquidity)),
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
        # Outcome rows: name fills what the bar + price + change columns leave.
        # Narrow rails (medium-tier 38-col preview) drop the bar rather than
        # wrap every row onto two lines.
        bar_w = BAR_W if w >= 38 else 0
        name_w = max(12, w - 16 - (bar_w + 1 if bar_w else 0))
        out = Text()
        out.append(event.title + "\n", style="bold")
        meta = []
        if event.end_date:
            meta.append(f"ends {fmt.end_date(event.end_date)}")
        if event.volume_24hr:
            meta.append(f"vol24h {fmt.vol(event.volume_24hr)}")
        if event.liquidity:
            meta.append(f"liq {fmt.vol(event.liquidity)}")
        if meta:
            out.append("  ".join(meta) + "\n", style="dim")
        out.append("\n")

        markets = event.active_markets
        for market in markets[:PREVIEW_OUTCOMES]:
            price = market.yes_price
            out.append(f"{fmt.trunc(market.display_title, name_w):<{name_w + 1}}", style="")
            if bar_w:
                out.append_text(prob_bar(price, bar_w))
            out.append(f"{fmt.cents(price):>7}", style="bold")
            change = market.one_day_price_change
            if change:
                style = UP if change > 0 else DOWN
                # Same format as every other 24h column (event table, market
                # preview): signed cents with the unit.
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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Throttled: re-rendering the preview per key-repeat row makes the
        # compositor repaint the pane ~20x/s while scrolling.
        self._follow = CursorFollow(self, self._show_slug)

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

    def _show_slug(self, slug: str) -> None:
        self.preview.show_event(self.table.events_by_slug.get(slug))

    def _preview_slug(self, slug: str | None) -> None:
        if slug:
            self._follow(slug)

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
