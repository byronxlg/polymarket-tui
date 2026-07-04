"""Column widgets for the experimental Miller-columns navigation.

Miller columns (a.k.a. cascading lists / column view - the pattern macOS
Finder's column view uses) show a drill hierarchy as a row of side-by-side
lists: each column lists the children of the row selected in the column to
its left. Here we render a sliding two-wide viewport over that stack, so
drilling deeper shifts the columns leftward.

These widgets are the per-level bodies. The sliding/viewport logic lives in
ui/screens/columns.py. `right`/`enter` drill in (via the DataTable
RowSelected message); `left` steps the viewport out one level, surfaced to
the screen as a MillerBack message rather than the app-wide nav_back.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Market
from polymarket_tui.ui.widgets.event_table import EventsTable, change_text
from polymarket_tui.ui.widgets.preview import MarketPreview
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class MillerBack(Message):
    """left pressed inside a column - step the viewport out one level.

    Distinct from the app's nav_back (which pops the whole screen); the
    columns screen consumes this to slide back before it ever pops.
    """

    def __init__(self, sender: Widget) -> None:
        super().__init__()
        self.sender = sender


# right drills in (select_cursor -> RowSelected); left steps out within the
# columns instead of delegating to app.nav_back like a normal VimDataTable.
_MILLER_BINDINGS = [
    Binding("right", "select_cursor", "open", show=False),
    Binding("left", "miller_back", "back", show=False),
]


class _MillerMixin:
    def action_miller_back(self) -> None:
        self.post_message(MillerBack(self))


class CategoryTable(_MillerMixin, VimDataTable):
    """Level 0: the top-nav categories, as a plain single-column list."""

    BINDINGS = _MILLER_BINDINGS

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", **kwargs)

    def on_mount(self) -> None:
        self.add_column("Category", width=18, key="cat")

    def set_categories(self, categories: list[tuple[str, str]]) -> None:
        self.clear()
        for label, slug in categories:
            self.add_row(label, key=slug)


class EventsColumn(_MillerMixin, EventsTable):
    """Level 1: events in the selected category (reuses the shared table)."""

    BINDINGS = _MILLER_BINDINGS


class OutcomesTable(_MillerMixin, VimDataTable):
    """Level 2: the outcome markets of the selected event."""

    BINDINGS = _MILLER_BINDINGS

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.markets_by_slug: dict[str, Market] = {}

    def on_mount(self) -> None:
        self.add_column("Outcome", width=30, key="outcome")
        self.add_column("Price", width=7, key="price")
        self.add_column("24h", width=7, key="change")

    def set_markets(self, markets: list[Market]) -> None:
        self.clear()
        self.markets_by_slug.clear()
        for market in markets:
            self.markets_by_slug[market.slug] = market
            self.add_row(
                fmt.trunc(market.display_title, 30),
                Text(fmt.cents(market.yes_price), style="bold cyan"),
                change_text(market.one_day_price_change),
                key=market.slug,
            )

    def highlighted_market(self) -> Market | None:
        if self.cursor_row is None or self.row_count == 0:
            return None
        row_key = self.coordinate_to_cell_key((self.cursor_row, 0)).row_key
        return self.markets_by_slug.get(str(row_key.value))


class DetailColumn(VerticalScroll):
    """Leaf level: a detail rail for one market. Focusable so left steps out."""

    BINDINGS = [Binding("left", "miller_back", "back", show=False)]
    can_focus = True

    def compose(self):
        yield MarketPreview(id="miller-detail-preview")

    def action_miller_back(self) -> None:
        self.post_message(MillerBack(self))

    def show(self, market: Market | None) -> None:
        self.query_one(MarketPreview).show_market(market)


class MillerColumn(Vertical):
    """A titled wrapper around one level's body widget."""

    def __init__(self, title: str, body: Widget, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_class("miller-col")
        self._title = title
        self._body = body

    def compose(self):
        yield Static(self._title, classes="miller-head")
        yield self._body

    @property
    def body(self) -> Widget:
        return self._body

    def set_title(self, title: str) -> None:
        self.query_one(".miller-head", Static).update(title)

    def focus_inner(self) -> None:
        self._body.focus()
