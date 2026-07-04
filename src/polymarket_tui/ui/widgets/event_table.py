"""Shared events table used by Home, Watchlist, and Search screens."""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.tiers import ColumnSpec, Tier, effective_tier, fit_columns
from polymarket_tui.ui.widgets.vim_table import VimDataTable


def change_text(change: float | None) -> Text:
    if change is None:
        return Text("-", style="dim")
    style = "green" if change > 0 else "red" if change < 0 else "dim"
    return Text(fmt.cents(change, signed=True), style=style)


# (key, label, width) per width tier. Compact keeps only what identifies the
# event and its price so a 30% pane never clips columns; medium drops the
# lowest-value column (Ends) and narrows the text columns.
TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("star", " ", 1),
        ("event", "Event", 46),
        ("outcome", "Top outcome", 24),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("vol", "Vol 24h", 9),
        ("ends", "Ends", 8),
    ),
    "medium": (
        ("star", " ", 1),
        ("event", "Event", 38),
        ("outcome", "Top outcome", 18),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("vol", "Vol 24h", 9),
    ),
    "compact": (
        ("star", " ", 1),
        ("event", "Event", 26),
        ("price", "Price", 7),
        ("change", "24h", 7),
    ),
}


class EventsTable(VimDataTable):
    """DataTable keyed by event slug; keeps the Event objects for row lookups.

    Tier-aware: apply_tier() records the pane's slot tier as a cap and the
    table refits itself on every resize - it picks the widest column set
    that both the cap allows and its measured width fits (DataTable columns
    can't be changed from CSS).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.events_by_slug: dict[str, Event] = {}
        self._cap: Tier = "full"
        self._columns_spec: list[ColumnSpec] = list(TIER_COLUMNS["full"])
        self._events: list[Event] = []
        self._watched: set[str] = set()

    def on_mount(self) -> None:
        self._build_columns()

    def on_resize(self) -> None:
        self._refit()

    def apply_tier(self, tier: Tier) -> None:
        """Record the slot tier cap; the next refit applies it."""
        self._cap = tier
        self._refit()

    def _refit(self) -> None:
        width = self.size.width
        if width <= 0:
            return  # not laid out yet; the first real resize refits
        tier = effective_tier(self._cap, width, TIER_COLUMNS)
        spec = fit_columns(TIER_COLUMNS[tier], width, "event")
        if spec == self._columns_spec and self.columns:
            return
        self._columns_spec = spec
        cursor = self.cursor_row
        self._build_columns()
        self._render_rows(self._events)
        if cursor is not None and self.row_count:
            self.move_cursor(row=min(cursor, self.row_count - 1))

    def _build_columns(self) -> None:
        self.clear(columns=True)
        for key, label, width in self._columns_spec:
            self.add_column(label, width=width, key=key)

    def set_events(self, events: list[Event], watched: set[str], clear: bool = True) -> None:
        if clear:
            self.clear()
            self.events_by_slug.clear()
            self._events = []
        self._watched = set(watched)
        fresh = [e for e in events if e.slug not in self.events_by_slug]
        for event in fresh:
            self.events_by_slug[event.slug] = event
        self._events.extend(fresh)
        self._render_rows(fresh)

    def _render_rows(self, events: list[Event]) -> None:
        widths = {key: width for key, _, width in self._columns_spec}
        for event in events:
            cells = self._row_cells(event, widths)
            self.add_row(*(cells[key] for key in widths), key=event.slug)

    def _row_cells(self, event: Event, widths: dict[str, int]) -> dict[str, object]:
        top = event.top_market
        outcome = ""
        price: Text | str = ""
        if top is not None:
            outcome = top.display_title if not event.is_binary else "Yes"
            price = Text(fmt.cents(top.yes_price), style="bold cyan")
        ends = fmt.end_date(event.end_date)
        return {
            "star": Text("*", style="yellow") if event.slug in self._watched else " ",
            "event": fmt.trunc(event.title, widths["event"]),
            "outcome": fmt.trunc(outcome, widths.get("outcome", 24)),
            "price": price,
            "change": change_text(top.one_day_price_change if top else None),
            "vol": fmt.money(event.volume_24hr),
            "ends": Text(ends, style="dim red") if ends == "ended" else ends,
        }

    def highlighted_event(self) -> Event | None:
        if self.cursor_row is None or self.row_count == 0:
            return None
        row_key = self.coordinate_to_cell_key((self.cursor_row, 0)).row_key
        return self.events_by_slug.get(str(row_key.value))

    def set_star(self, slug: str, watched: bool) -> None:
        # Track in _watched too so a tier rebuild re-renders the star.
        (self._watched.add if watched else self._watched.discard)(slug)
        if slug in self.events_by_slug:
            self.update_cell(slug, "star", Text("*", style="yellow") if watched else " ")
