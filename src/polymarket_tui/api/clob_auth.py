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

from polymarket_tui.core.auth import AuthError, bootstrap_authed_client
from polymarket_tui.core.config import Settings
from polymarket_tui.models.portfolio import OpenOrder

log = logging.getLogger(__name__)


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
