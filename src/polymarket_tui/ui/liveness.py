"""May this widget still touch its children? (guards for async UI tails)

Worker tails, call_after_refresh callbacks, and timers can fire while
NavHost is tearing a pane down. Removal is asynchronous: there is a window
where the pane still reports is_mounted=True but its children are already
pruned, so a query_one there panics the whole app. NavHost._discard stamps
the pane and every descendant with `_nav_discarded = True` synchronously
BEFORE starting the removal; `alive()` is the guard the tails check.
"""

from __future__ import annotations

from textual.widget import Widget


def alive(widget: Widget) -> bool:
    return widget.is_mounted and not getattr(widget, "_nav_discarded", False)
