"""Miller-columns browse navigation over the events hierarchy.

The root pane is the events list (with category tabs on top, like the home
screen); drilling in opens a 30/70 split - the parent shrinks to 30% and the
opened pane takes 70%:

    Events -> Outcomes -> Detail

Interaction:
- right/enter drills in: opens the child level in a new 70% right pane and
  moves the cursor into it (parent shrinks to 30%).
- left moves back to the parent WITHOUT closing the child; pressing left again
  from the parent slides the viewport out one level (and at the root leaves
  the screen).
- right while in the right pane slides that pane to the left (30%) and opens a
  fresh child on the right (70%).

A breadcrumb keeps the full path in view after ancestor panes slide off. The
child pane follows the parent's highlighted row (preview-follows-cursor). This
screen is additive - it does not touch the Home/Event/Market screen stack.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static, Tab, Tabs

from polymarket_tui.core import fmt
from polymarket_tui.ui.screens.home import CATEGORIES
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.miller import (
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
        Binding("tab", "next_tag", "category"),
        Binding("shift+tab", "prev_tag", "prev category", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Viewport state over the fixed 3-level stack (0=events, 1=outcomes,
        # 2=detail).
        self._focus = 0  # focused column
        self._left = 0  # column shown in the left viewport slot
        self._open = 0  # deepest column currently opened in the drill path
        # Selection made at each drill step, for the breadcrumb trail. _sel[c]
        # names the row picked in column c-1 that opened column c (index 0
        # unused - column 0 is the events list root).
        self._sel = ["", "", ""]
        self._tag_slug: str | None = None
        self._cat_label = CATEGORIES[0][0]

    def compose(self) -> ComposeResult:
        yield AppHeader("browse")
        yield Static(id="miller-crumbs")
        yield Tabs(*(Tab(label, id=slug) for label, slug in CATEGORIES), id="col-tags")
        self._events = EventsColumn(id="miller-events")
        self._outcomes = OutcomesTable(id="miller-outcomes")
        self._detail = DetailColumn(id="miller-detail")
        self._wrap = [
            MillerColumn("Events", self._events, id="mcol-0"),
            MillerColumn("Outcomes", self._outcomes, id="mcol-1"),
            MillerColumn("Detail", self._detail, id="mcol-2"),
        ]
        with Horizontal(id="miller-viewport"):
            yield from self._wrap
        yield Footer()

    def on_mount(self) -> None:
        self.title = "browse"
        self.query_one(Tabs).can_focus = False
        self._load_events(self._tag_slug)
        self._reflow()

    # -- category tabs (drive the root events list) --------------------------

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        slug = event.tab.id
        self._cat_label = next((label for label, s in CATEGORIES if s == slug), slug or "")
        self._tag_slug = None if slug == "trending" else slug
        # Changing category collapses any drill back to the root events list.
        self._focus = self._left = self._open = 0
        self._sel = ["", "", ""]
        self._load_events(self._tag_slug)
        self._reflow()

    def action_next_tag(self) -> None:
        self.query_one(Tabs).action_next_tab()

    def action_prev_tag(self) -> None:
        self.query_one(Tabs).action_previous_tab()

    # -- drill (right/enter) --------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._drill()

    def _drill(self) -> None:
        i = self._focus
        if i >= 2:  # detail is a leaf
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
            # In the right pane: fall back to the parent, keep the child open.
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
            event = self._events.highlighted_event()
            if event is None:
                return False
            markets = event.active_markets
            self._sel[1] = event.title
            self._wrap[1].set_title(fmt.trunc(event.title, 40))
            self._outcomes.set_markets(markets)
            self._update_crumbs()
            return bool(markets)
        if parent == 1:
            market = self._outcomes.highlighted_market()
            if market is None:
                return False
            self._sel[2] = market.display_title
            self._wrap[2].set_title(fmt.trunc(market.display_title, 40))
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
        if i < 2 and i < self._open:
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
        in view after ancestor panes have slid off the left edge. Rooted at the
        active category (which also shows as the selected tab)."""
        rightmost = min(self._left + 1, self._open)
        crumb = Text()
        crumb.append(" " + self._cat_label, style="bold" if self._focus == 0 else "dim")
        for level in range(1, rightmost + 1):
            crumb.append("  ›  ", style="dim")
            style = "bold" if level == self._focus else "dim"
            crumb.append(fmt.trunc(self._sel[level] or "…", 34), style=style)
        self.query_one("#miller-crumbs", Static).update(crumb)

    def action_refresh(self) -> None:
        self._load_events(self._tag_slug)
