"""MarketChannel dispatch, subscribe, and reconnect (issue #1), no real network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from polymarket_tui.api.ws import MarketChannel

FIXTURES = Path(__file__).parent / "fixtures"


def _book_frame() -> tuple[str, str]:
    raw = json.loads((FIXTURES / "ws_market_book.json").read_text())[0]
    return raw["asset_id"], json.dumps([raw])  # frames arrive array-wrapped


class FakeWS:
    """Yields queued frames. When empty it either holds the connection open
    (blocks) or reports it closed, to exercise the live vs reconnect paths."""

    def __init__(self, frames: list[str], *, drop_when_empty: bool = False) -> None:
        self._frames = list(frames)
        self._drop = drop_when_empty
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._drop:
            raise ConnectionError("closed")  # triggers the reconnect path
        await asyncio.Event().wait()  # hold the connection open until cancelled
        raise AssertionError("unreachable")

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_channel_subscribes_and_applies_book():
    asset_id, frame = _book_frame()
    got = asyncio.Event()
    events: list[tuple[str, str]] = []

    def on_update(kind: str, aid: str) -> None:
        events.append((kind, aid))
        if kind == "book" and aid == asset_id:
            got.set()

    connections: list[FakeWS] = []

    async def fake_connect(url: str) -> FakeWS:
        ws = FakeWS([frame])
        connections.append(ws)
        return ws

    ch = MarketChannel([asset_id], on_update, connect=fake_connect)
    ch.start()
    await asyncio.wait_for(got.wait(), timeout=2)

    assert ("book", asset_id) in events
    assert ch.book(asset_id) is not None
    assert ch.status() == "live"
    # The subscribe frame was sent with the asset id.
    sub = json.loads(connections[0].sent[0])
    assert sub == {"type": "market", "assets_ids": [asset_id]}

    await ch.stop()


@pytest.mark.asyncio
async def test_channel_reconnects_after_drop():
    asset_id, frame = _book_frame()
    connects = 0
    reconnected = asyncio.Event()

    async def fake_connect(url: str) -> FakeWS:
        nonlocal connects
        connects += 1
        if connects >= 2:
            reconnected.set()
        return FakeWS([frame], drop_when_empty=True)  # each connection drops after one frame

    ch = MarketChannel([asset_id], lambda *_: None, connect=fake_connect)
    # Speed up the backoff for the test.
    import polymarket_tui.api.ws as ws_mod

    original = ws_mod._BACKOFF
    ws_mod._BACKOFF = [0.01]
    try:
        ch.start()
        await asyncio.wait_for(reconnected.wait(), timeout=2)
        assert connects >= 2  # it re-established the connection after the drop
    finally:
        ws_mod._BACKOFF = original
        await ch.stop()


@pytest.mark.asyncio
async def test_status_down_before_connect():
    ch = MarketChannel(["A"], lambda *_: None, connect=None)
    assert ch.status() == "down"
    assert ch.book("A") is None


def test_status_transitions_drive_the_badge_and_fallback():
    import time

    import polymarket_tui.api.ws as ws_mod

    ch = MarketChannel(["A"], lambda *_: None)
    # Disconnected -> down (UI shows 'polling', REST drives the book).
    assert ch.status() == "down"
    # Connected with a fresh frame -> live (WS owns the book).
    ch._connected = True
    ch._last_msg = time.monotonic()
    assert ch.status() == "live"
    # Connected but no frames for STALE_AFTER_S -> stale (falls back to polling).
    ch._last_msg = time.monotonic() - (ws_mod.STALE_AFTER_S + 1)
    assert ch.status() == "stale"
