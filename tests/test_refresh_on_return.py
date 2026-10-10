"""Refresh-on-return staleness gate (ui/staleness.py).

The mixin's clock is faked by patching the module's monotonic, so the
tests walk time forward explicitly.
"""

from __future__ import annotations

import pytest

from polymarket_tui.ui import staleness
from polymarket_tui.ui.staleness import STALE_AFTER_S, RefreshOnReturn


class FakePane(RefreshOnReturn):
    def __init__(self) -> None:
        self.refreshes = 0
        self.ok = True

    def refresh_on_return_ok(self) -> bool:
        return self.ok

    def refresh_stale(self) -> None:
        self.refreshes += 1


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(staleness, "monotonic", clock)
    return clock


def test_first_check_stamps_without_refreshing(clock: Clock) -> None:
    # The first check lands right after on_mount's initial load.
    pane = FakePane()
    pane.refresh_if_stale()
    assert pane.refreshes == 0
    clock.now += STALE_AFTER_S + 1
    pane.refresh_if_stale()
    assert pane.refreshes == 1


def test_fresh_pane_does_not_refresh(clock: Clock) -> None:
    pane = FakePane()
    pane.refresh_if_stale()
    clock.now += STALE_AFTER_S - 1
    pane.refresh_if_stale()
    assert pane.refreshes == 0


def test_refresh_restamps(clock: Clock) -> None:
    pane = FakePane()
    pane.refresh_if_stale()
    clock.now += STALE_AFTER_S + 1
    pane.refresh_if_stale()
    pane.refresh_if_stale()
    assert pane.refreshes == 1
    clock.now += STALE_AFTER_S + 1
    pane.refresh_if_stale()
    assert pane.refreshes == 2


def test_veto_blocks_without_stamping(clock: Clock) -> None:
    # A vetoed refresh (armed cancel strip, deep scroll) must retry as
    # soon as the veto lifts, not wait out another staleness window.
    pane = FakePane()
    pane.refresh_if_stale()
    clock.now += STALE_AFTER_S + 1
    pane.ok = False
    pane.refresh_if_stale()
    assert pane.refreshes == 0
    pane.ok = True
    pane.refresh_if_stale()
    assert pane.refreshes == 1


def test_default_refresh_stale_calls_action_refresh(clock: Clock) -> None:
    class ActionPane(RefreshOnReturn):
        def __init__(self) -> None:
            self.actions = 0

        def action_refresh(self) -> None:
            self.actions += 1

    pane = ActionPane()
    pane.refresh_if_stale()
    clock.now += STALE_AFTER_S + 1
    pane.refresh_if_stale()
    assert pane.actions == 1


def test_all_drill_panes_opt_in() -> None:
    from polymarket_tui.ui.screens.event import EventPane
    from polymarket_tui.ui.screens.home import HomePane
    from polymarket_tui.ui.screens.market import MarketPane
    from polymarket_tui.ui.screens.portfolio import PortfolioPane
    from polymarket_tui.ui.screens.user import UserPane
    from polymarket_tui.ui.screens.watchlist import WatchlistPane

    for pane in (HomePane, EventPane, MarketPane, PortfolioPane, UserPane, WatchlistPane):
        assert issubclass(pane, RefreshOnReturn), pane.__name__
