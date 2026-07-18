"""Refresh-on-return: a pane the user comes back to reloads if it went stale.

Drill panes stay mounted while hidden (NavHost re-shows them on back
navigation instead of rebuilding), so a pane whose data loads once in
on_mount shows that first snapshot forever. NavHost calls
refresh_if_stale() whenever a pane regains focus after a reflow and when
the base screen resumes from an overlay (search, reader, related, a
modal); the pane reloads only if its last load is older than
STALE_AFTER_S, so rapid back-and-forth navigation costs nothing.
"""

from __future__ import annotations

from time import monotonic

STALE_AFTER_S = 30.0


class RefreshOnReturn:
    """Mixin for drill panes hosted by NavHost.

    The default refresh_stale() reuses the pane's action_refresh (the
    global R), which every pane already keeps cursor-safe. Override
    refresh_stale() when returning should reload less than R does, and
    refresh_on_return_ok() to veto a reload the pane's current state
    can't absorb (an armed cancel strip, a deep-scrolled list).
    """

    # Class-level default: instances stamp their own on first check.
    _fresh_at: float | None = None

    def mark_fresh(self) -> None:
        self._fresh_at = monotonic()

    def refresh_if_stale(self) -> None:
        if self._fresh_at is None:
            # First check lands right after on_mount kicked off the
            # initial load - stamp it, nothing to refresh yet.
            self.mark_fresh()
            return
        if monotonic() - self._fresh_at < STALE_AFTER_S:
            return
        if not self.refresh_on_return_ok():
            # Not stamped: the next return retries once the veto lifts.
            return
        self.mark_fresh()
        self.refresh_stale()

    def refresh_on_return_ok(self) -> bool:
        return True

    def refresh_stale(self) -> None:
        self.action_refresh()
