"""Experimental Miller-columns navigation over the browse hierarchy.

A sliding two-wide viewport over a four-level drill stack:

    Categories -> Events -> Outcomes -> Detail

Interaction (as requested for UX evaluation):
- right/enter drills in: opens the child level in a new right pane and moves
  the cursor into it.
- left moves back to the left pane WITHOUT closing the right pane; pressing
  left again from the left pane slides the viewport out one level (and at the
  root leaves the screen).
- right while already in the right pane slides that pane into the left slot
  and opens a fresh child on the right.

The child pane always reflects the parent's highlighted row (preview-follows-
cursor), matching the rest of the app. This screen is additive - it does not
touch the existing push/pop screen stack used by Home/Event/Market.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from polymarket_tui.core import fmt
from polymarket_tui.ui.screens.home import CATEGORIES
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.miller import (
    CategoryTable,
    DetailColumn,
    EventsColumn,
    MillerBack,
    MillerColumn,
    OutcomesTable,
)

EVENTS_LIMIT = 50


class ColumnsScreen(Screen):
    BINDINGS = [
        Binding("escape", "step_back", "back", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Viewport state over the fixed 4-level stack (indices 0..3).
        self._focus = 0  # focused column
        self._left = 0  # column shown in the left viewport slot
        self._open = 0  # deepest column currently opened in the drill path
        # Selection made at each drill step, for the breadcrumb trail. _sel[c]
        # names the row picked in column c-1 that opened column c (index 0
        # unused - column 0 is the root category picker).
        self._sel = ["", "", "", ""]

    def compose(self) -> ComposeResult:
        yield AppHeader("columns")
        yield Static(id="miller-crumbs")
        self._cat = CategoryTable(id="miller-cat")
        self._events = EventsColumn(id="miller-events")
        self._outcomes = OutcomesTable(id="miller-outcomes")
        self._detail = DetailColumn(id="miller-detail")
        self._wrap = [
            MillerColumn("Categories", self._cat, id="mcol-0"),
            MillerColumn("Events", self._events, id="mcol-1"),
            MillerColumn("Outcomes", self._outcomes, id="mcol-2"),
            MillerColumn("Detail", self._detail, id="mcol-3"),
        ]
        with Horizontal(id="miller-viewport"):
            yield from self._wrap
        yield Footer()

    def on_mount(self) -> None:
        self.title = "columns"
        self._cat.set_categories(CATEGORIES)
        self._reflow()

    # -- drill (right/enter) --------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._drill()

    def _drill(self) -> None:
        i = self._focus
        if i >= 3:  # detail is a leaf
            return
        if i == self._open:  # first time opening this child - populate it
            if not self._build_child(i):
                return
            self._open = i + 1
        self._focus = i + 1
        self._left = self._focus - 1
        self._reflow()

    # -- step out (left / escape) --------------------------------------------

    def on_miller_back(self, message: MillerBack) -> None:
        self.action_step_back()

    def action_step_back(self) -> None:
        if self._focus == self._left + 1:
            # In the right pane: fall back to the left pane, keep right open.
            self._focus = self._left
            self._reflow()
            return
        # In the left pane.
        if self._left == 0:
            self.app.pop_screen()
            return
        # Slide the viewport out one level; the focused column becomes the
        # right pane and its parent reappears on the left.
        self._left -= 1
        self._reflow()

    # -- child population -----------------------------------------------------

    def _build_child(self, parent: int) -> bool:
        """Populate column parent+1 from the parent's highlighted row.

        Returns False when there is nothing to drill into.
        """
        if parent == 0:
            label, slug = CATEGORIES[self._cat.cursor_row or 0]
            self._sel[1] = label
            self._wrap[1].set_title(label)
            self._load_events(None if slug == "trending" else slug)
            self._update_crumbs()
            return True
        if parent == 1:
            event = self._events.highlighted_event()
            if event is None:
                return False
            markets = event.active_markets
            self._sel[2] = event.title
            self._wrap[2].set_title(fmt.trunc(event.title, 40))
            self._outcomes.set_markets(markets)
            self._update_crumbs()
            return bool(markets)
        if parent == 2:
            market = self._outcomes.highlighted_market()
            if market is None:
                return False
            self._sel[3] = market.display_title
            self._wrap[3].set_title(fmt.trunc(market.display_title, 40))
            self._detail.show(market)
            self._update_crumbs()
            return True
        return False

    @work(exclusive=True, group="miller-events")
    async def _load_events(self, tag_slug: str | None) -> None:
        try:
            events = await self.app.gamma.events(
                limit=EVENTS_LIMIT, order="volume24hr", tag_slug=tag_slug
            )
        except Exception as exc:
            self.notify(f"Failed to load events: {exc}", severity="error", timeout=6)
            return
        events = [e for e in events if e.top_market is not None]
        self._events.set_events(events, set(self.app.watchlist.slugs), clear=True)

    # -- preview-follows-cursor: refresh an open child when the parent moves --

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        i = self._focus
        # Only when the moving column is focused and already has an open child.
        if i < 3 and i < self._open:
            self._build_child(i)

    # -- render ---------------------------------------------------------------

    def _reflow(self) -> None:
        # When a child is open, the parent shrinks to 30% (kept visible for
        # context) and the just-opened child takes 70%. A lone root pane fills
        # the width.
        child_open = self._left + 1 <= self._open
        for i, wrap in enumerate(self._wrap):
            visible = i in (self._left, self._left + 1) and i <= self._open
            wrap.display = visible
            wrap.set_class(i == self._focus, "focused")
            wrap.set_class(visible and child_open and i == self._left, "col-parent")
            wrap.set_class(visible and i == self._left + 1, "col-child")
        self._update_crumbs()
        self.call_after_refresh(self._wrap[self._focus].focus_inner)

    def _update_crumbs(self) -> None:
        """Breadcrumb trail to the deepest visible pane - keeps the full path
        in view even after ancestor panes have slid off the left edge."""
        rightmost = min(self._left + 1, self._open)
        crumb = Text()
        crumb.append(" Browse", style="bold" if self._focus == 0 else "dim")
        for level in range(1, rightmost + 1):
            crumb.append("  ›  ", style="dim")
            style = "bold" if level == self._focus else "dim"
            crumb.append(fmt.trunc(self._sel[level] or "…", 34), style=style)
        self.query_one("#miller-crumbs", Static).update(crumb)

    def action_refresh(self) -> None:
        if self._open >= 1:
            self._build_child(0)
