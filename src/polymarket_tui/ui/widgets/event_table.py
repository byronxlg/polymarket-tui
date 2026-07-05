"""Shared events table used by Home, Watchlist, and Search screens."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event
from polymarket_tui.ui.theme import AMBER, BLUE, DOWN, UP
from polymarket_tui.ui.tiers import ColumnSpec, Tier, effective_tier, fit_columns
from polymarket_tui.ui.widgets.vim_table import VimDataTable


def change_text(change: float | None) -> Text:
    if change is None:
        return Text("-", style="dim", justify="right")
    style = UP if change > 0 else DOWN if change < 0 else "dim"
    return Text(fmt.cents(change, signed=True), style=style, justify="right")


# (key, label, width) per width tier. Compact keeps only what identifies the
# event and its price so a 30% pane never clips columns; medium drops the
# lowest-value column (Ends) and narrows the text columns.
TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("star", " ", 2),
        ("event", "Event", 46),
        ("outcome", "Top outcome", 24),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("vol", "Vol 24h", 9),
    ),
    "medium": (
        ("star", " ", 2),
        ("event", "Event", 38),
        ("outcome", "Top outcome", 18),
        ("price", "Price", 7),
        ("change", "24h", 7),
        ("vol", "Vol 24h", 9),
    ),
    "compact": (
        ("star", " ", 2),
        ("event", "Event", 26),
        ("price", "Price", 7),
        ("change", "24h", 7),
    ),
}

# Spacious re-composes the row instead of padding it (the MS Teams
# comfy/compact model): two-line rows where the second line carries the
# context columns - the metadata line replaces the Vol column and the 24h
# change stacks under the price, so the freed width goes to full titles.
SPACIOUS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("star", " ", 2),
        ("event", "Event", 52),
        ("outcome", "Top outcome", 22),
        ("price", "Price", 8),
    ),
    "medium": (
        ("star", " ", 2),
        ("event", "Event", 42),
        ("outcome", "Top outcome", 16),
        ("price", "Price", 8),
    ),
    "compact": (
        ("star", " ", 2),
        ("event", "Event", 26),
        ("price", "Price", 8),
    ),
}


def event_meta(event: Event) -> str:
    """The dim second line of a spacious row: ends Jul 20 · vol24h $41M · liq $53M.

    Same vocabulary and order as the market header so the two read as one
    system. Missing fields drop out instead of rendering '-'.
    """
    parts = []
    if event.end_date is not None:
        parts.append(f"ends {fmt.end_date(event.end_date)}")
    if event.volume_24hr is not None:
        parts.append(f"vol24h {fmt.vol(event.volume_24hr)}")
    if event.liquidity is not None:
        parts.append(f"liq {fmt.vol(event.liquidity)}")
    return " · ".join(parts)


class EventsTable(VimDataTable):
    """DataTable keyed by event slug; keeps the Event objects for row lookups.

    Tier-aware: apply_tier() records the pane's slot tier as a cap and the
    table refits itself on every resize - it picks the widest column set
    that both the cap allows and its measured width fits (DataTable columns
    can't be changed from CSS).
    """

    # DataTable hides its enter binding; the primary action must be visible
    # in the footer for casual users (journey review, 2026-07-05).
    BINDINGS = [Binding("enter", "select_cursor", "open")]

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.events_by_slug: dict[str, Event] = {}
        self._cap: Tier = "full"
        self._density: str = "condensed"
        self._columns_spec: list[ColumnSpec] = list(TIER_COLUMNS["full"])
        self._events: list[Event] = []
        self._watched: set[str] = set()
        self._ordered: set[str] = set()  # slugs where the user has a resting order

    def on_mount(self) -> None:
        self._density = getattr(self.app, "density", "condensed")
        self.cell_padding = 2 if self._density == "spacious" else 1
        self._build_columns()

    def on_resize(self) -> None:
        self._refit()

    def apply_tier(self, tier: Tier) -> None:
        """Record the slot tier cap; the next refit applies it."""
        self._cap = tier
        self._refit()

    def on_density_changed(self, density: str) -> None:
        """T toggled: re-compose rows (called by the app, not Textual)."""
        if density == self._density:
            return
        self._density = density
        self.cell_padding = 2 if density == "spacious" else 1
        self._columns_spec = []  # force the refit past its no-change guard
        self._refit()

    @property
    def _spacious(self) -> bool:
        return self._density == "spacious"

    def _refit(self) -> None:
        width = self.size.width
        if width <= 0:
            return  # not laid out yet; the first real resize refits
        tier_columns = SPACIOUS_TIER_COLUMNS if self._spacious else TIER_COLUMNS
        pad = self.cell_padding
        tier = effective_tier(self._cap, width, tier_columns, pad)
        lengths = [len(e.title) for e in self._events]
        if self._spacious:
            lengths += [len(event_meta(e)) for e in self._events]
        flex_max = max(lengths, default=0) or None
        spec = fit_columns(tier_columns[tier], width, "event", flex_max, pad)
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

    def set_events(
        self,
        events: list[Event],
        watched: set[str],
        clear: bool = True,
        ordered: set[str] | None = None,
    ) -> None:
        if clear:
            self.clear()
            self.events_by_slug.clear()
            self._events = []
        self._watched = set(watched)
        if ordered is not None:
            # Appended pages carry flags for their own events only - merge,
            # or earlier rows would lose their resting-order flag on rebuild.
            self._ordered = set(ordered) if clear else self._ordered | set(ordered)
        fresh = [e for e in events if e.slug not in self.events_by_slug]
        for event in fresh:
            self.events_by_slug[event.slug] = event
        self._events.extend(fresh)
        self._render_rows(fresh)
        self._refit()  # the longest title may have changed

    def _render_rows(self, events: list[Event]) -> None:
        widths = {key: width for key, _, width in self._columns_spec}
        height = 2 if self._spacious else 1
        for event in events:
            cells = (self._spacious_cells if self._spacious else self._row_cells)(
                event, widths
            )
            self.add_row(*(cells[key] for key in widths), key=event.slug, height=height)

    def _row_cells(self, event: Event, widths: dict[str, int]) -> dict[str, object]:
        top = event.top_market
        outcome = ""
        price: Text | str = ""
        if top is not None:
            outcome = top.display_title if not event.is_binary else "Yes"
            price = Text(fmt.cents(top.yes_price), style="bold", justify="right")
        return {
            "star": self._flag_cell(event.slug),
            "event": fmt.trunc(event.title, widths["event"]),
            "outcome": fmt.trunc(outcome, widths.get("outcome", 24)),
            "price": price,
            "change": change_text(top.one_day_price_change if top else None),
            "vol": Text(fmt.vol(event.volume_24hr), justify="right"),
        }

    def _spacious_cells(self, event: Event, widths: dict[str, int]) -> dict[str, object]:
        """Two-line row: title over a dim metadata line; 24h stacks under price."""
        top = event.top_market
        w = widths["event"]
        title = Text(fmt.trunc(event.title, w))
        title.append("\n" + fmt.trunc(event_meta(event), w), style="dim")
        price = Text(justify="right")
        outcome = ""
        if top is not None:
            outcome = top.display_title if not event.is_binary else "Yes"
            price.append(fmt.cents(top.yes_price), style="bold")
            price.append("\n")
            price.append_text(change_text(top.one_day_price_change))
        return {
            "star": self._flag_cell(event.slug),
            "event": title,
            "outcome": fmt.trunc(outcome, widths.get("outcome", 22)),
            "price": price,
        }

    def _flag_cell(self, slug: str) -> Text:
        """Two-char flag: * watched, o resting order."""
        out = Text()
        out.append("*" if slug in self._watched else " ", style=AMBER)
        out.append("o" if slug in self._ordered else " ", style=f"bold {BLUE}")
        return out

    def highlighted_event(self) -> Event | None:
        if self.cursor_row is None or self.row_count == 0:
            return None
        row_key = self.coordinate_to_cell_key((self.cursor_row, 0)).row_key
        return self.events_by_slug.get(str(row_key.value))

    def set_star(self, slug: str, watched: bool) -> None:
        # Track in _watched too so a tier rebuild re-renders the star.
        (self._watched.add if watched else self._watched.discard)(slug)
        if slug in self.events_by_slug:
            self.update_cell(slug, "star", self._flag_cell(slug))
