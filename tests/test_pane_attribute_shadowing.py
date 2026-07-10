"""Drill panes must not name an instance attribute something Textual owns.

A pane that stores state under a name its Textual base class already uses gets
it silently clobbered at runtime. `self._closed = []` for closed positions was
the real case: MessagePump sets `self._closed = True` when the widget shuts
down, so the list turned into a bool and _refit died iterating it. Nothing in a
pure-row unit test catches this - it only bites once the widget mounts.
"""

from __future__ import annotations

import ast
import inspect

import pytest
from textual.containers import Vertical

from polymarket_tui.ui.screens.event import EventPane
from polymarket_tui.ui.screens.home import HomePane
from polymarket_tui.ui.screens.portfolio import PortfolioPane
from polymarket_tui.ui.screens.user import UserPane
from polymarket_tui.ui.screens.watchlist import WatchlistPane

PANES = [HomePane, PortfolioPane, UserPane, WatchlistPane, EventPane]


def _assigned_in_init(cls: type) -> set[str]:
    """Names bound by `self.<name> = ...` in the class's own __init__."""
    tree = ast.parse(inspect.getsource(cls.__init__).lstrip())
    names: set[str] = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            for leaf in ast.walk(target):
                if (
                    isinstance(leaf, ast.Attribute)
                    and isinstance(leaf.value, ast.Name)
                    and leaf.value.id == "self"
                ):
                    names.add(leaf.attr)
    return names


# Everything a bare Textual container already carries: instance attrs set by
# its __init__, plus the class-level API surface.
TEXTUAL_OWNED = set(vars(Vertical())) | set(dir(Vertical))


@pytest.mark.parametrize("pane", PANES, ids=lambda c: c.__name__)
def test_pane_does_not_shadow_a_textual_attribute(pane: type) -> None:
    clashes = _assigned_in_init(pane) & TEXTUAL_OWNED
    assert not clashes, (
        f"{pane.__name__}.__init__ assigns {sorted(clashes)}, which Textual's "
        f"Widget/MessagePump already owns. Either the framework overwrites the "
        f"pane's state (_closed) or the pane overwrites the framework's (_name, "
        f"which is the widget's DOM name). Pick another name."
    )


def test_the_guard_can_actually_see_a_clash() -> None:
    # Guard the guard: _closed is the name that bit us, and it must still be
    # one Textual owns (otherwise this whole file passes vacuously).
    assert "_closed" in TEXTUAL_OWNED

    class Shadowing(Vertical):
        def __init__(self) -> None:
            super().__init__()
            self._closed: list[int] = []

    assert _assigned_in_init(Shadowing) & TEXTUAL_OWNED == {"_closed"}
