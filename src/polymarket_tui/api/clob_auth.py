"""Authenticated CLOB access: balance, open orders, and (later) order placement.

py-clob-client-v2 is synchronous; every call goes through asyncio.to_thread.
The client is bootstrapped lazily on first use and cached.
"""

from __future__ import annotations

import asyncio
import logging

from polymarket_tui.core.auth import AuthError, bootstrap_authed_client
from polymarket_tui.core.config import Settings
from polymarket_tui.models.portfolio import OpenOrder

log = logging.getLogger(__name__)


class AuthedClobClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        self._lock = asyncio.Lock()
        self.auth_failed: str | None = None

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
        ba = await asyncio.to_thread(
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
        raw = await asyncio.to_thread(client.get_open_orders, OpenOrderParams())
        return [OpenOrder.model_validate(o) for o in raw]

    async def cancel_order(self, order_id: str) -> dict:
        client = await self._get_client()
        return await asyncio.to_thread(client.cancel, order_id)

    async def create_and_post_order(self, order_args, order_type) -> dict:
        """Sign and post. Caller (OrderService) owns validation and the live gate."""
        client = await self._get_client()

        def _run() -> dict:
            signed = client.create_order(order_args)
            return client.post_order(signed, order_type)

        return await asyncio.to_thread(_run)

    async def sign_order(self, order_args) -> object:
        """Sign without posting - used by dry-run to prove the signing path."""
        client = await self._get_client()
        return await asyncio.to_thread(client.create_order, order_args)
