"""Spacious density re-composes rows (two-line cells), not just padding.

Covers the pure row builders; the live toggle path is exercised in the
journey harness (T on home / a trader profile).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rich.text import Text

from polymarket_tui.models.market import Event
from polymarket_tui.models.portfolio import Position
from polymarket_tui.ui.tiers import columns_need, effective_tier
from polymarket_tui.ui.widgets.event_table import SPACIOUS_TIER_COLUMNS, event_meta
from polymarket_tui.ui.widgets.tables import (
    POSITIONS_SPACIOUS_TIER_COLUMNS,
    position_meta,
    position_row,
)


def _event(**kwargs) -> Event:
    return Event(slug="e", title="Will it rain tomorrow?", **kwargs)


def _position() -> Position:
    return Position(
        slug="m",
        title="Will it rain tomorrow?",
        outcome="Yes",
        size=1200.0,
        avg_price=0.334,
        cur_price=0.358,
        current_value=429.6,
        cash_pnl=28.8,
        percent_pnl=7.2,
    )


def test_event_meta_joins_present_fields() -> None:
    ends = datetime.now(UTC) + timedelta(days=10)
    meta = event_meta(_event(end_date=ends, volume_24hr=41_100_000, liquidity=53_300))
    assert meta.startswith("ends ")
    assert "vol24h $41.1M" in meta
    assert "liq $53K" in meta
    assert meta.count("·") == 2


def test_event_meta_drops_missing_fields() -> None:
    assert event_meta(_event(volume_24hr=500.0)) == "vol24h $500"
    assert event_meta(_event()) == ""


def test_position_row_spacious_recomposes() -> None:
    row = position_row(_position(), tier="full", density="spacious")
    # market, cur, value, pnl - outcome/size/avg fold into the meta line
    assert len(row) == 4
    market = row[0]
    assert isinstance(market, Text)
    title_line, meta_line = market.plain.split("\n")
    assert title_line == "Will it rain tomorrow?"
    assert meta_line == "Yes · 1.2K sh · avg 33.4c"
    pnl = row[-1]
    assert isinstance(pnl, Text)
    assert pnl.plain == "+28.80\n+7%"


def test_position_meta_matches_condensed_columns() -> None:
    assert position_meta(_position()) == "Yes · 1.2K sh · avg 33.4c"


def test_position_row_condensed_unchanged() -> None:
    row = position_row(_position(), tier="full")
    assert len(row) == 7  # market, outcome, size, avg, cur, value, pnl
    assert row[0] == "Will it rain tomorrow?"


def test_spacious_tiers_respect_wider_padding() -> None:
    # cell_padding 2 costs 4 cells per column; the fit math must account
    # for it or spacious tables would render clipped columns.
    cols = SPACIOUS_TIER_COLUMNS["compact"]
    assert columns_need(cols, pad=2) == columns_need(cols, pad=1) + 2 * len(cols)
    narrow = columns_need(SPACIOUS_TIER_COLUMNS["medium"], pad=2) - 1
    assert effective_tier("full", narrow, SPACIOUS_TIER_COLUMNS, pad=2) == "compact"


def test_positions_spacious_columns_defined_for_all_tiers() -> None:
    assert set(POSITIONS_SPACIOUS_TIER_COLUMNS) == {"full", "medium", "compact"}
