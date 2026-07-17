"""Authenticated CLOB access: balance, open orders, and (later) order placement.

py-clob-client-v2 is synchronous; every call goes through asyncio.to_thread.
The client is bootstrapped lazily on first use and cached. The client wraps a
single requests.Session, which is not thread-safe, so all calls are serialized
through a lock - concurrent workers (a portfolio refresh while an order posts)
must not touch the shared session at the same time.

The lock is a threading.Lock acquired INSIDE the worker thread, not an
asyncio.Lock around the await: to_thread is uncancellable, so when a caller's
wait_for timeout cancels the await, the orphaned thread keeps running in the
Session - an asyncio lock would already be released and the next call would
run concurrently with it. The thread-level lock keeps the orphan exclusive.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from decimal import Decimal, InvalidOperation

from polymarket_tui.core.auth import AuthError, bootstrap_authed_client
from polymarket_tui.core.config import Settings
from polymarket_tui.models.portfolio import OpenOrder

log = logging.getLogger(__name__)


def _tick_cache(client) -> dict | None:
    """py-clob-client-v2's per-token tick cache: a name-mangled ``__tick_sizes``
    dict on the client (mangled to the class that defines it, ``ClobClient``).
    Found by suffix rather than a hard-coded ``_ClobClient__tick_sizes`` so a
    client subclass or rename degrades to a no-op refresh instead of silently
    signing against a stale tick. The client exposes no public way to refresh."""
    for name, value in vars(client).items():
        if name.endswith("__tick_sizes") and isinstance(value, dict):
            return value
    return None


class AuthedClobClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        self._lock = asyncio.Lock()  # guards lazy bootstrap
        self._call_lock = threading.Lock()  # serializes the non-thread-safe client
        self.auth_failed: str | None = None

    async def _call(self, fn, *args):
        """Run one client call in a thread, serialized at thread level (see
        module docstring for why the lock must live inside the thread)."""

        def _locked():
            with self._call_lock:
                return fn(*args)

        return await asyncio.to_thread(_locked)

    async def _get_client(self):
        async with self._lock:
            if self._client is None:
                try:
                    self._client = await bootstrap_authed_client(self._settings)
                    self.auth_failed = None
                except AuthError as exc:
                    self.auth_failed = str(exc)
                    raise
            return self._client

    async def usdc_balance(self) -> float:
        """USDC collateral balance in dollars."""
        from py_clob_client_v2 import AssetType, BalanceAllowanceParams

        client = await self._get_client()
        ba = await self._call(
            client.get_balance_allowance,
            BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self._settings.polymarket_signature_type,
            ),
        )
        return int(ba["balance"]) / 1_000_000

    async def open_orders(self) -> list[OpenOrder]:
        from py_clob_client_v2 import OpenOrderParams

        client = await self._get_client()
        raw = await self._call(client.get_open_orders, OpenOrderParams())
        return [OpenOrder.model_validate(o) for o in raw]

    async def cancel_order(self, order_id: str) -> dict:
        from py_clob_client_v2 import OrderPayload

        client = await self._get_client()
        return await self._call(client.cancel_order, OrderPayload(orderID=order_id))

    async def resolved_tick(self, token_id: str, *, refresh: bool = True) -> Decimal | None:
        """The tick py-clob-client-v2 will actually sign this token at.

        The client caches a token's tick for the whole session (get_tick_size)
        and never refreshes it, and its price_valid only bounds-checks - so if a
        market re-grids 0.01 -> 0.001 mid-session (as its price nears 0/1), the
        client can still hold the stale coarse tick and silently round the price
        DOWN when it signs (98.1c -> 98.0c). The app's live book is the authority
        on the current tick; this lets OrderService compare the two before it
        posts and refuse to sign a price the client would alter.

        `refresh` drops the client's cached tick first so get_tick_size re-reads
        the exchange's current value. Best-effort: returns None if the tick can't
        be read (the caller then proceeds as before - a dropped cache still makes
        the next resolve fresh, so no regression). Reaching into the client's
        name-mangled cache is deliberate - the client exposes no public refresh.
        """
        def _read(client) -> object:
            if refresh:
                cache = _tick_cache(client)
                if cache is not None:
                    cache.pop(token_id, None)
            return client.get_tick_size(token_id)

        # Never raise: a tick that cannot be read (auth bootstrap failure, network,
        # unexpected shape) returns None, and place() proceeds down its normal
        # signing path where those failures are already handled. Dropping the cache
        # above still makes the next resolve fresh, so there is no regression.
        try:
            client = await self._get_client()
            raw = await self._call(_read, client)
            return Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError, KeyError):
            return None
        except Exception:
            log.warning("could not resolve tick for %s", token_id, exc_info=True)
            return None

    async def create_and_post_order(self, order_args, order_type) -> dict:
        """Sign and post. Caller (OrderService) owns validation and the live gate."""
        client = await self._get_client()

        def _run() -> dict:
            signed = client.create_order(order_args)
            return client.post_order(signed, order_type)

        return await self._call(_run)

    async def sign_order(self, order_args) -> object:
        """Sign without posting - used by dry-run to prove the signing path."""
        client = await self._get_client()
        return await self._call(client.create_order, order_args)
