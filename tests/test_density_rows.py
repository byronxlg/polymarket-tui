"""Spacious density re-composes rows (two-line cells), not just padding.

Covers the pure row builders; the live toggle path is exercised in the
journey harness (T on home / a trader profile).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.models.portfolio import ActivityItem, OpenOrder, Position
from polymarket_tui.ui.screens.event import MARKETS_SPACIOUS_TIER_COLUMNS, market_meta
from polymarket_tui.ui.screens.portfolio import ORDERS_SPACIOUS_TIER_COLUMNS, _order_meta
from polymarket_tui.ui.tiers import columns_need, effective_tier
from polymarket_tui.ui.widgets.event_table import SPACIOUS_TIER_COLUMNS, event_meta
from polymarket_tui.ui.widgets.tables import (
    ACTIVITY_SPACIOUS_TIER_COLUMNS,
    POSITIONS_SPACIOUS_TIER_COLUMNS,
    activity_meta,
    activity_row,
    position_meta,
    position_row,
)


def _event(**kwargs) -> Event:
    return Event(slug="e", title="Will it rain tomorrow?", **kwargs)


def _activity() -> ActivityItem:
    return ActivityItem(
        type="TRADE",
        side="BUY",
        size=1200.0,
        price=0.334,
        outcome="Yes",
        title="Will it rain tomorrow?",
        timestamp=1_700_000_000,
    )


def _order() -> OpenOrder:
    return OpenOrder(
        side="BUY",
        outcome="Yes",
        price=0.334,
        original_size=200.0,
        size_matched=50.0,
        created_at=1_700_000_000,
    )


def _market() -> Market:
    return Market(
        question="Will it rain tomorrow?",
        best_bid=0.33,
        best_ask=0.34,
        spread=0.01,
        volume_24hr=41_100_000,
    )


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
    assert row[0].plain == "Will it rain tomorrow?"


def test_spacious_tiers_respect_wider_padding() -> None:
    # cell_padding 2 costs 4 cells per column; the fit math must account
    # for it or spacious tables would render clipped columns.
    cols = SPACIOUS_TIER_COLUMNS["compact"]
    assert columns_need(cols, pad=2) == columns_need(cols, pad=1) + 2 * len(cols)
    narrow = columns_need(SPACIOUS_TIER_COLUMNS["medium"], pad=2) - 1
    assert effective_tier("full", narrow, SPACIOUS_TIER_COLUMNS, pad=2) == "compact"


def test_positions_spacious_columns_defined_for_all_tiers() -> None:
    assert set(POSITIONS_SPACIOUS_TIER_COLUMNS) == {"full", "medium", "compact"}


def _won_position() -> Position:
    pos = _position()
    return pos.model_copy(update={"redeemable": True, "cur_price": 1.0})


def test_position_row_marks_redeemable_win_when_asked() -> None:
    row = position_row(_won_position(), tier="medium", mark_won=True)
    assert row[0].plain.endswith(" (won)")
    # full tier has the verbose flag column instead - no marker unless asked
    row = position_row(_won_position(), tier="full")
    assert not row[0].plain.endswith("(won)")


def test_position_row_spacious_meta_carries_redeem_hint() -> None:
    row = position_row(_won_position(), tier="full", density="spacious", mark_won=True)
    assert "won - redeem on web" in row[0].plain


# -- activity (portfolio History + trader Activity) ---------------------------


def test_activity_meta_recomposes_columns() -> None:
    meta = activity_meta(_activity())
    # when/type/side/outcome/price/size all fold onto the dim line
    assert "BUY Yes @ 33.4c" in meta
    assert "1.2K sh" in meta


def test_activity_row_spacious_recomposes() -> None:
    row = activity_row(_activity(), tier="full", density="spacious")
    assert len(row) == 2  # market (2-line), usdc - everything else folds in
    market = row[0]
    assert isinstance(market, Text)
    title_line, meta_line = market.plain.split("\n")
    assert title_line == "Will it rain tomorrow?"
    assert "BUY Yes @ 33.4c" in meta_line
    assert row[1] == fmt.money(_activity().usdc_size)


def test_activity_row_condensed_unchanged() -> None:
    row = activity_row(_activity(), tier="full")
    # when/type/side/market/outcome/price/size/usdc
    assert len(row) == 8


def test_activity_spacious_columns_defined_for_all_tiers() -> None:
    assert set(ACTIVITY_SPACIOUS_TIER_COLUMNS) == {"full", "medium", "compact"}


# -- open orders (portfolio) --------------------------------------------------


def test_order_meta_recomposes_columns() -> None:
    meta = _order_meta(_order())
    assert meta.startswith("BUY Yes")
    assert "50 filled" in meta
    assert "placed " in meta


def test_orders_spacious_columns_defined_for_all_tiers() -> None:
    assert set(ORDERS_SPACIOUS_TIER_COLUMNS) == {"full", "medium", "compact"}


# -- event markets (event detail outcome list) --------------------------------


def test_market_meta_recomposes_columns() -> None:
    meta = market_meta(_market())
    assert f"bid {fmt.cents(0.33)}" in meta
    assert f"ask {fmt.cents(0.34)}" in meta
    assert "vol $41.1M" in meta
    # spread is dropped (derivable from bid/ask) to make room for volume
    assert "spr" not in meta


def test_markets_spacious_columns_defined_for_all_tiers() -> None:
    assert set(MARKETS_SPACIOUS_TIER_COLUMNS) == {"full", "medium", "compact"}
