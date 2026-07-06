"""refresh_after_fill wiring: which panes a /ws/user event refreshes.

The backoff polling itself needs the live app; what must not regress is
the routing - a fill event refreshes exactly the panes whose market it
touches, matched by asset id or condition id.
"""

from __future__ import annotations

from polymarket_tui.models.market import Market
from polymarket_tui.ui.screens.market import MarketPane


def make_pane() -> MarketPane:
    market = Market(
        slug="will-it-rain",
        question="Will it rain?",
        conditionId="0xcond",
        clobTokenIds='["tok-yes", "tok-no"]',
    )
    return MarketPane(market)


def test_involves_matches_by_asset_id() -> None:
    pane = make_pane()
    assert pane.involves("tok-yes", "")
    assert pane.involves("tok-no", "")
    assert not pane.involves("tok-other", "")


def test_involves_matches_by_condition_id() -> None:
    pane = make_pane()
    assert pane.involves("", "0xcond")
    assert not pane.involves("", "0xother")


def test_involves_ignores_empty_event_fields() -> None:
    # A message with neither field must not match every pane.
    pane = make_pane()
    assert not pane.involves("", "")
