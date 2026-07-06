"""Portfolio service: cached positions/balance/value shared by screens."""

from __future__ import annotations

import asyncio
import time

from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.api.data import DataApiClient
from polymarket_tui.core.config import Settings
from polymarket_tui.models.market import Event
from polymarket_tui.models.portfolio import ActivityItem, OpenOrder, Position

POSITIONS_TTL = 30.0
VALUE_TTL = 60.0
ORDERS_TTL = 15.0


class PortfolioService:
    def __init__(
        self, settings: Settings, data: DataApiClient, authed: AuthedClobClient | None
    ) -> None:
        self._settings = settings
        self._data = data
        self._authed = authed
        self._positions: list[Position] = []
        self._positions_at = 0.0
        self._value: float | None = None
        self._value_at = 0.0
        self._balance: float | None = None
        self._balance_at = 0.0
        self._orders: list[OpenOrder] = []
        self._orders_at = 0.0

    @property
    def user(self) -> str:
        return self._settings.polymarket_funder

    def invalidate(self) -> None:
        self._positions_at = 0.0
        self._value_at = 0.0
        self._balance_at = 0.0
        self._orders_at = 0.0

    async def positions(self, force: bool = False) -> list[Position]:
        if not self.user:
            return []
        now = time.monotonic()
        if force or now - self._positions_at > POSITIONS_TTL:
            self._positions = await self._data.positions(self.user)
            self._positions_at = now
        return self._positions

    def position_for(self, token_id: str) -> Position | None:
        return next((p for p in self._positions if p.asset == token_id), None)

    async def portfolio_value(self, force: bool = False) -> float | None:
        if not self.user:
            return None
        now = time.monotonic()
        if force or now - self._value_at > VALUE_TTL:
            self._value = await self._data.portfolio_value(self.user)
            self._value_at = now
        return self._value

    async def usdc_balance(self, force: bool = False) -> float | None:
        if self._authed is None:
            return None
        now = time.monotonic()
        if force or now - self._balance_at > VALUE_TTL:
            # py-clob rides requests with no timeout - a stalled call would
            # otherwise pin "loading balances..." (and the header) forever.
            self._balance = await asyncio.wait_for(self._authed.usdc_balance(), timeout=10)
            self._balance_at = now
        return self._balance

    async def activity(self, limit: int = 100) -> list[ActivityItem]:
        if not self.user:
            return []
        return await self._data.activity(self.user, limit=limit)

    async def open_orders(self, force: bool = False) -> list[OpenOrder]:
        if self._authed is None:
            return []
        now = time.monotonic()
        if force or now - self._orders_at > ORDERS_TTL:
            self._orders = await asyncio.wait_for(self._authed.open_orders(), timeout=10)
            self._orders_at = now
        return self._orders

    def orders_for_assets(self, token_ids: set[str]) -> list[OpenOrder]:
        """Cached view - callers await open_orders() first to (re)fill it."""
        return [o for o in self._orders if o.asset_id in token_ids]

    def order_condition_ids(self) -> set[str]:
        """Condition ids with at least one resting order (cached view)."""
        return {o.market for o in self._orders if o.market}

    def position_condition_ids(self) -> set[str]:
        """Condition ids you hold shares in (cached view - callers await
        positions() first). Resolved losses are dust, not holdings."""
        return {
            p.condition_id
            for p in self._positions
            if p.condition_id and p.size >= 0.01 and not p.resolved_loss
        }

    async def flag_slugs(self, events: list[Event]) -> tuple[set[str], set[str]]:
        """(ordered, held) slugs among `events` for list-row flags: resting
        orders need full auth, holdings show in observer mode too."""
        ordered_cond: set[str] = set()
        held_cond: set[str] = set()
        if self._settings.can_auth:
            try:
                await self.open_orders()
                ordered_cond = self.order_condition_ids()
            except Exception:
                pass
        if self._settings.can_read_portfolio:
            try:
                await self.positions()
                held_cond = self.position_condition_ids()
            except Exception:
                pass

        def slugs(cond: set[str]) -> set[str]:
            if not cond:
                return set()
            return {e.slug for e in events if any(m.condition_id in cond for m in e.markets)}

        return slugs(ordered_cond), slugs(held_cond)
