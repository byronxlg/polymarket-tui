"""NavHost: the base screen that hosts the 30/70 sliding drill navigation.

Instead of push/pop full-window screens, drilling mounts the real screen
bodies (HomePane, EventPane, MarketPane, ...) side by side. Only two levels
show at once: the parent shrinks to 30% (kept visible/interactive) and the
just-opened child takes 70%. Deeper drilling slides the stack left; a
breadcrumb keeps the full path in view.

right/enter (a pane's RowSelected -> app.open_*) drills; left/esc flows
through app.nav_back -> NavHost.handle_back: from the child it focuses the
parent (child stays open), from the parent it slides the viewport out a level.
The focused pane's own handle_back (e.g. MarketPane closing an armed order
panel) runs first, preserving the money-path step-out order.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Static

from polymarket_tui.core import fmt
from polymarket_tui.ui.screens.home import HomePane
from polymarket_tui.ui.widgets.app_header import AppHeader


class NavHost(Screen):
    # Hidden order-panel inputs must not steal autofocus (see MarketPane);
    # NavHost drives focus explicitly after every reflow.
    AUTO_FOCUS = None

    def __init__(self) -> None:
        super().__init__()
        self._panes: list[Widget] = []
        self._crumbs: list[str] = []
        self._focus = 0  # index of the focused pane
        self._left = 0  # index of the pane in the left viewport slot

    def compose(self) -> ComposeResult:
        yield AppHeader(HomePane.header_title)
        yield Static(id="nav-crumbs")
        root = HomePane()
        root.add_class("nav-pane")
        self._panes = [root]
        self._crumbs = ["Home"]
        with Horizontal(id="nav-viewport"):
            yield root
        yield Footer()

    def on_mount(self) -> None:
        self._reflow()

    # -- drill / back ---------------------------------------------------------

    def drill(self, pane: Widget, crumb: str) -> None:
        """Open `pane` as the 70% child of the currently focused pane."""
        # Drop any stale deeper panes left over from a previous drill.
        for stale in self._panes[self._focus + 1 :]:
            stale.remove()
        del self._panes[self._focus + 1 :]
        del self._crumbs[self._focus + 1 :]
        pane.add_class("nav-pane")
        self.query_one("#nav-viewport").mount(pane)
        self._panes.append(pane)
        self._crumbs.append(crumb)
        self._focus = len(self._panes) - 1
        self._left = self._focus - 1
        self._reflow()

    def handle_back(self) -> bool:
        """left/esc: pane-internal step-out first, then cross-pane viewport.

        Always returns True - NavHost is the base screen and never pops.
        """
        pane = self._panes[self._focus]
        pane_back = getattr(pane, "handle_back", None)
        if pane_back is not None and pane_back():
            return True
        if self._focus == self._left + 1:
            # In the child: fall back to the parent, keep the child open.
            self._focus = self._left
            self._reflow()
            return True
        if self._left == 0:
            return True  # at the root - nothing to slide out to
        # Slide the viewport out one level; the focused pane becomes the child
        # slot and its parent reappears on the left.
        self._left -= 1
        self._reflow()
        return True

    def reset_to_root(self) -> None:
        """Collapse the drill stack back to the root pane (used by 'home')."""
        for stale in self._panes[1:]:
            stale.remove()
        del self._panes[1:]
        del self._crumbs[1:]
        self._focus = self._left = 0
        self._reflow()

    # -- render ---------------------------------------------------------------

    def _reflow(self) -> None:
        n = len(self._panes)
        child_open = self._left + 1 < n
        for i, pane in enumerate(self._panes):
            visible = i in (self._left, self._left + 1)
            pane.display = visible
            pane.set_class(i == self._focus, "focused")
            pane.set_class(visible and child_open and i == self._left, "col-parent")
            pane.set_class(visible and i == self._left + 1, "col-child")
        header = self.query_one(AppHeader)
        header.set_title(getattr(self._panes[self._focus], "header_title", "polymarket-tui"))
        self._update_crumbs()
        self.call_after_refresh(self._focus_inner)

    def _focus_inner(self) -> None:
        pane = self._panes[self._focus]
        focus_inner = getattr(pane, "focus_inner", None)
        if focus_inner is not None:
            focus_inner()

    def _update_crumbs(self) -> None:
        crumbs = self.query_one("#nav-crumbs", Static)
        # No trail to show at the root - it's just the home page.
        crumbs.display = len(self._panes) > 1
        top = min(self._left + 1, len(self._panes) - 1)
        text = Text()
        for i in range(top + 1):
            if i > 0:
                text.append("  ›  ", style="dim")
            style = "bold" if i == self._focus else "dim"
            text.append(fmt.trunc(self._crumbs[i], 34), style=style)
        self.query_one("#nav-crumbs", Static).update(text)
