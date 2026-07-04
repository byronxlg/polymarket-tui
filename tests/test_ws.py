"""Market-channel WS frame parsing and live book maintenance (issue #1).

Exercised against real captured frames in tests/fixtures/ws_market_*.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from polymarket_tui.models.ws import (
    BookMessage,
    LastTradeMessage,
    LiveBook,
    PriceChangeMessage,
    parse_market_message,
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
    assert parse_market_message({"event_type": "tick_size_change"}) is None
    assert parse_market_message({}) is None


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
