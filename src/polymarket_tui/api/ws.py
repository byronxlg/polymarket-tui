"""CLOB market-channel websocket manager (issue #1).

Maintains a live order book for one or more assets over
wss://ws-subscriptions-clob.polymarket.com/ws/market, with reconnect/backoff,
resubscribe-on-reconnect, keepalive, and staleness tracking. The UI degrades to
REST polling with a stale badge whenever `status()` reports the socket unhealthy.

Frames arrive batched as a JSON array; each element has an `event_type`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable

import websockets

from polymarket_tui.models.market import OrderBook
from polymarket_tui.models.ws import (
    BookMessage,
    LastTradeMessage,
    LiveBook,
    PriceChangeMessage,
    UserOrderMessage,
    UserTradeMessage,
    parse_market_message,
    parse_user_message,
)

log = logging.getLogger(__name__)

MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
USER_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
PING_INTERVAL_S = 10.0
# On a quiet market the only inbound frames are PONG replies to our keepalive,
# arriving every PING_INTERVAL_S - so "stale" must allow for at least two full
# keepalive cycles or a healthy idle socket flaps stale (and the UI falls back
# to spurious REST fetches) for ~2s of every 10s.
STALE_AFTER_S = 25.0
_BACKOFF = [0.5, 1.0, 2.0, 5.0, 10.0]
# A session must survive this long for the backoff to reset. Resetting on the
# handshake alone turns an accept-then-close server (e.g. rejected ws auth)
# into a tight 0.5s reconnect hammer.
STABLE_SESSION_S = 30.0

# (kind, asset_id) -> called on the event loop after a frame is applied.
UpdateCallback = Callable[[str, str], None]


class MarketChannel:
    def __init__(
        self,
        asset_ids: list[str],
        on_update: UpdateCallback,
        *,
        url: str = MARKET_WS_URL,
        connect: Callable[[str], Awaitable] | None = None,
    ) -> None:
        self._assets = list(dict.fromkeys(asset_ids))  # de-dupe, keep order
        self._on_update = on_update
        self._url = url
        self._connect = connect or self._default_connect
        self._books: dict[str, LiveBook] = {a: LiveBook() for a in self._assets}
        self._trades: dict[str, LastTradeMessage] = {}
        self._task: asyncio.Task | None = None
        self._ws = None
        self._connected = False
        self._last_msg: float = 0.0

    @staticmethod
    async def _default_connect(url: str):
        return await websockets.connect(url, ping_interval=None, max_size=None)

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close_ws()

    async def _close_ws(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._connected = False

    # -- state accessors -----------------------------------------------------

    def book(self, asset_id: str) -> OrderBook | None:
        lb = self._books.get(asset_id)
        return lb.order_book() if lb and lb.applied else None

    def last_trade(self, asset_id: str) -> LastTradeMessage | None:
        return self._trades.get(asset_id)

    @property
    def connected(self) -> bool:
        return self._connected

    def seconds_since_message(self) -> float:
        return time.monotonic() - self._last_msg if self._last_msg else float("inf")

    def status(self) -> str:
        """'live' | 'stale' | 'down' - drives the UI badge and REST fallback."""
        if not self._connected:
            return "down"
        return "live" if self.seconds_since_message() < STALE_AFTER_S else "stale"

    # -- run loop ------------------------------------------------------------

    async def _run(self) -> None:
        attempt = 0
        while True:
            session_started: float | None = None
            try:
                self._ws = await self._connect(self._url)
                self._connected = True
                session_started = time.monotonic()
                await self._subscribe()
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # connection dropped or failed
                log.debug("market ws error: %s", exc)
            finally:
                await self._close_ws()
            # Backoff resets only after a session that held long enough to be
            # healthy - never on the handshake alone (see STABLE_SESSION_S).
            if session_started is not None:
                if time.monotonic() - session_started >= STABLE_SESSION_S:
                    attempt = 0
            delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
            attempt += 1
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise

    async def _subscribe(self) -> None:
        await self._ws.send(json.dumps({"type": "market", "assets_ids": self._assets}))

    async def _read_loop(self) -> None:
        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=PING_INTERVAL_S)
            except TimeoutError:
                await self._ws.send("PING")  # keepalive; server may close idle sockets
                continue
            self._last_msg = time.monotonic()
            self._dispatch(raw if isinstance(raw, str) else raw.decode())

    def _dispatch(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        for raw in payload if isinstance(payload, list) else [payload]:
            if not isinstance(raw, dict):
                continue
            msg = parse_market_message(raw)
            if msg is None:
                continue
            self._apply(msg)

    def _apply(self, msg: object) -> None:
        if isinstance(msg, BookMessage):
            lb = self._books.get(msg.asset_id)
            if lb and lb.apply_book(msg):
                self._emit("book", msg.asset_id)
        elif isinstance(msg, PriceChangeMessage):
            for asset_id, lb in self._books.items():
                if lb.apply_price_change(msg, asset_id):
                    self._emit("price_change", asset_id)
        elif isinstance(msg, LastTradeMessage):
            self._trades[msg.asset_id] = msg
            self._emit("last_trade_price", msg.asset_id)

    def _emit(self, kind: str, asset_id: str) -> None:
        try:
            self._on_update(kind, asset_id)
        except Exception:  # a UI callback must never kill the socket loop
            log.exception("market ws update callback failed")


# (kind, message) -> called on the event loop for own order/trade updates.
UserCallback = Callable[[str, object], None]


class UserChannel:
    """Authenticated /ws/user socket: own order and fill updates in real time.

    Same reconnect/backoff/keepalive discipline as MarketChannel. Emits parsed
    UserOrderMessage / UserTradeMessage to the callback so the UI can refresh the
    open-orders tab and toast fills without a manual refresh.
    """

    def __init__(
        self,
        creds: dict,
        on_event: UserCallback,
        *,
        url: str = USER_WS_URL,
        connect: Callable[[str], Awaitable] | None = None,
    ) -> None:
        self._creds = creds
        self._on_event = on_event
        self._url = url
        self._connect = connect or self._default_connect
        self._task: asyncio.Task | None = None
        self._ws = None
        self._connected = False

    @staticmethod
    async def _default_connect(url: str):
        return await websockets.connect(url, ping_interval=None, max_size=None)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close_ws()

    async def _close_ws(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def _run(self) -> None:
        attempt = 0
        while True:
            session_started: float | None = None
            try:
                self._ws = await self._connect(self._url)
                self._connected = True
                session_started = time.monotonic()
                await self._ws.send(
                    json.dumps({"type": "user", "markets": [], "auth": self._creds})
                )
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("user ws error: %s", exc)
            finally:
                await self._close_ws()
            # As in MarketChannel: only a session that held resets the backoff.
            # Rejected ws auth is an accept-then-close - it must keep escalating.
            if session_started is not None:
                if time.monotonic() - session_started >= STABLE_SESSION_S:
                    attempt = 0
            delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
            attempt += 1
            await asyncio.sleep(delay)

    async def _read_loop(self) -> None:
        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=PING_INTERVAL_S)
            except TimeoutError:
                await self._ws.send("PING")
                continue
            self._dispatch(raw if isinstance(raw, str) else raw.decode())

    def _dispatch(self, text: str) -> None:
        if text == "PONG":
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        for raw in payload if isinstance(payload, list) else [payload]:
            if not isinstance(raw, dict):
                continue
            msg = parse_user_message(raw)
            if isinstance(msg, UserOrderMessage):
                self._emit("order", msg)
            elif isinstance(msg, UserTradeMessage):
                self._emit("trade", msg)

    def _emit(self, kind: str, msg: object) -> None:
        try:
            self._on_event(kind, msg)
        except Exception:
            log.exception("user ws event callback failed")
