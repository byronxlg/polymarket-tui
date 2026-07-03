"""Async client for data-api.polymarket.com (portfolio, activity - keyed by address)."""

from __future__ import annotations

from typing import Any

import httpx

from polymarket_tui.models.portfolio import ActivityItem, Position

BASE_URL = "https://data-api.polymarket.com"


class DataApiClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._http = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=15.0,
            http2=True,
            headers={"User-Agent": "polymarket-tui/0.1"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def positions(self, user: str, limit: int = 200) -> list[Position]:
        data = await self._get("/positions", {"user": user, "limit": limit, "sortBy": "CURRENT"})
        return [Position.model_validate(p) for p in data]

    async def portfolio_value(self, user: str) -> float | None:
        data = await self._get("/value", {"user": user})
        if isinstance(data, list) and data:
            return float(data[0].get("value", 0.0))
        return None

    async def activity(self, user: str, limit: int = 100) -> list[ActivityItem]:
        data = await self._get("/activity", {"user": user, "limit": limit})
        return [ActivityItem.model_validate(a) for a in data]
