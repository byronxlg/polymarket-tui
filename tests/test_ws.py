"""Market-channel WS frame parsing and live book maintenance (issue #1).

Exercised against real captured frames in tests/fixtures/ws_market_*.json.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from polymarket_tui.models.ws import (
    BookMessage,
    LastTradeMessage,
    LiveBook,
    PriceChangeMessage,
    TickSizeChangeMessage,
    UserOrderMessage,
    parse_market_message,
    parse_user_message,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def test_parse_real_book_frame():
    raw = _load("ws_market_book.json")[0]
    msg = parse_market_message(raw)
    assert isinstance(msg, BookMessage)
    assert msg.asset_id
    assert msg.timestamp > 0
    assert msg.asks  # captured book had asks


def test_parse_real_price_change_frame():
    raw = _load("ws_market_price_change.json")[0]
    msg = parse_market_message(raw)
    assert isinstance(msg, PriceChangeMessage)
    assert msg.price_changes
    change = msg.price_changes[0]
    assert change.asset_id and change.side in ("BUY", "SELL")


def test_parse_real_last_trade_frame():
    raw = _load("ws_market_last_trade_price.json")[0]
    msg = parse_market_message(raw)
    assert isinstance(msg, LastTradeMessage)
    assert msg.side in ("BUY", "SELL")
    assert float(msg.price) >= 0


def test_unknown_event_type_is_none():
    assert parse_market_message({"event_type": "some_future_frame"}) is None
    assert parse_market_message({}) is None


def test_real_book_frame_carries_the_exchange_tick():
    """The book frame is where the tick comes from - dropping it made the panel
    render a 0.001 market at whole cents until the pane was reopened."""
    raw = _load("ws_market_book.json")[0]
    msg = parse_market_message(raw)
    assert msg.tick_size == Decimal("0.001")


def test_live_book_exposes_the_tick_and_keeps_it_across_deltas():
    book_raw = _load("ws_market_book.json")[0]
    lb = LiveBook()
    lb.apply_book(BookMessage.model_validate(book_raw))
    assert lb.order_book().tick_size == Decimal("0.001")

    # price_change frames never carry a tick; the book must not lose it.
    change_raw = _load("ws_market_price_change.json")[0]
    change = PriceChangeMessage.model_validate(change_raw)
    lb.apply_price_change(change, change.price_changes[0].asset_id)
    assert lb.order_book().tick_size == Decimal("0.001")


def test_tick_size_change_regrids_the_book():
    lb = LiveBook()
    lb.apply_book(BookMessage.model_validate(_load("ws_market_book.json")[0]))
    msg = parse_market_message(
        {
            "event_type": "tick_size_change",
            "asset_id": "1",
            "old_tick_size": "0.001",
            "new_tick_size": "0.0001",
        }
    )
    assert isinstance(msg, TickSizeChangeMessage)
    assert lb.apply_tick_size(msg) is True
    assert lb.order_book().tick_size == Decimal("0.0001")
    # The CLOB repeats the frame; a no-op change must not wake the UI.
    assert lb.apply_tick_size(msg) is False


def test_live_book_applies_snapshot():
    raw = _load("ws_market_book.json")[0]
    msg = BookMessage.model_validate(raw)
    book = LiveBook()
    assert book.apply_book(msg) is True
    ob = book.order_book()
    # Captured snapshot had empty bids; best ask is the lowest ask price.
    assert ob.best_ask is not None
    assert ob.best_ask.price == min(lvl.price for lvl in ob.asks)
    assert not ob.bids


def test_live_book_price_change_updates_level():
    book = LiveBook()
    snapshot = BookMessage(asset_id="A", timestamp=100, asks=[{"price": "0.50", "size": "10"}])
    book.apply_book(snapshot)
    # New ask level via a price_change for asset A.
    pc = PriceChangeMessage(
        timestamp=101,
        price_changes=[{"asset_id": "A", "price": "0.49", "size": "5", "side": "SELL"}],
    )
    assert book.apply_price_change(pc, "A") is True
    ob = book.order_book()
    assert ob.best_ask.price == 0.49
    assert ob.best_ask.size == 5


def test_live_book_price_change_zero_removes_level():
    book = LiveBook()
    book.apply_book(BookMessage(asset_id="A", timestamp=100, bids=[{"price": "0.40", "size": "8"}]))
    pc = PriceChangeMessage(
        timestamp=101,
        price_changes=[{"asset_id": "A", "price": "0.40", "size": "0", "side": "BUY"}],
    )
    book.apply_price_change(pc, "A")
    assert book.order_book().best_bid is None


def test_live_book_ignores_other_asset_changes():
    book = LiveBook()
    book.apply_book(BookMessage(asset_id="A", timestamp=100, bids=[{"price": "0.40", "size": "8"}]))
    pc = PriceChangeMessage(
        timestamp=101,
        price_changes=[{"asset_id": "B", "price": "0.40", "size": "0", "side": "BUY"}],
    )
    assert book.apply_price_change(pc, "A") is False
    assert book.order_book().best_bid.size == 8  # untouched


def test_live_book_discards_stale_frames():
    book = LiveBook()
    book.apply_book(BookMessage(asset_id="A", timestamp=200, bids=[{"price": "0.40", "size": "8"}]))
    # An older price_change must be dropped.
    stale = PriceChangeMessage(
        timestamp=150,
        price_changes=[{"asset_id": "A", "price": "0.40", "size": "0", "side": "BUY"}],
    )
    assert book.apply_price_change(stale, "A") is False
    assert book.order_book().best_bid.size == 8


# -- user channel (issue #1) --------------------------------------------------


def test_parse_real_user_placement_frame():
    raw = _load("ws_user_order_placement.json")[0]
    msg = parse_user_message(raw)
    assert isinstance(msg, UserOrderMessage)
    assert msg.type == "PLACEMENT"
    assert msg.status == "LIVE"
    assert msg.resting is True
    assert msg.gone is False
    assert msg.side == "BUY"


def test_parse_real_user_cancellation_frame():
    raw = _load("ws_user_order_cancellation.json")[0]
    msg = parse_user_message(raw)
    assert isinstance(msg, UserOrderMessage)
    assert msg.type == "CANCELLATION"
    assert msg.status == "CANCELED"
    assert msg.resting is False
    assert msg.gone is True


def test_parse_user_unknown_type_is_none():
    assert parse_user_message({"event_type": "heartbeat"}) is None
    assert parse_user_message({}) is None


def test_user_order_matched_is_gone():
    msg = UserOrderMessage(status="MATCHED", original_size="5", size_matched="5")
    assert msg.gone is True
    assert msg.resting is False
