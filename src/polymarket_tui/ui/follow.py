"""Throttle for cursor-follow updates (rails/previews tracking a table cursor).

Holding an arrow key repeats at ~15-30 rows/s; re-rendering a preview pane -
or worse, kicking API fetches - per row turns scrolling into churn (profiled:
a full compositor pass per keypress, and fetch workers cancelling each other
faster than any can finish). CursorFollow calls through immediately when the
cursor has been idle (single presses feel instant) and otherwise coalesces
the burst into one trailing call per interval, so a held key settles into a
few updates per second and the final row always renders.
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Any


class CursorFollow:
    """Leading + trailing throttle bound to a widget's timer clock."""

    def __init__(self, widget, fn: Callable[..., None], interval: float = 0.15) -> None:
        self._widget = widget
        self._fn = fn
        self._interval = interval
        self._last = 0.0
        self._pending: tuple[Any, ...] | None = None
        self._timer_running = False

    def __call__(self, *args: Any) -> None:
        now = monotonic()
        if not self._timer_running and now - self._last >= self._interval:
            self._last = now
            self._fn(*args)
            return
        self._pending = args
        if not self._timer_running:
            self._timer_running = True
            self._widget.set_timer(self._interval, self._flush)

    def _flush(self) -> None:
        self._timer_running = False
        if self._pending is None:
            return
        args, self._pending = self._pending, None
        self._last = monotonic()
        self._fn(*args)
