"""Portfolio service: cached positions/balance/value shared by screens."""

from __future__ import annotations

import time

from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.api.data import DataApiClient
from polymarket_tui.core.config import Settings
from polymarket_tui.models.portfolio import ActivityItem, OpenOrder, Position

POSITIONS_TTL = 30.0
VALUE_TTL = 60.0


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

    @property
    def user(self) -> str:
        return self._settings.polymarket_funder

    def invalidate(self) -> None:
        self._positions_at = 0.0
        self._value_at = 0.0
        self._balance_at = 0.0

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
            self._balance = await self._authed.usdc_balance()
            self._balance_at = now
        return self._balance

    async def activity(self, limit: int = 100) -> list[ActivityItem]:
        if not self.user:
            return []
        return await self._data.activity(self.user, limit=limit)

    async def open_orders(self) -> list[OpenOrder]:
        if self._authed is None:
            return []
        return await self._authed.open_orders()
