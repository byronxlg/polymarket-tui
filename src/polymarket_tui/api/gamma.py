"""Async client for the Gamma discovery API (unauthenticated)."""

from __future__ import annotations

from typing import Any

import httpx

from polymarket_tui.models.market import Event, Market, Tag

BASE_URL = "https://gamma-api.polymarket.com"

SORT_ORDERS = ["volume24hr", "liquidity", "endDate", "startDate"]


class GammaClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._http = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=15.0,
            http2=True,
            headers={"User-Agent": "polymarket-tui/0.1"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order: str = "volume24hr",
        ascending: bool = False,
        tag_slug: str | None = None,
    ) -> list[Event]:
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "active": "true",
            "closed": "false",
            "archived": "false",
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if tag_slug:
            params["tag_slug"] = tag_slug
        data = await self._get("/events", params)
        return [Event.model_validate(e) for e in data]

    async def event_by_slug(self, slug: str) -> Event | None:
        data = await self._get("/events", {"slug": slug})
        if not data:
            return None
        return Event.model_validate(data[0])

    async def market_by_slug(self, slug: str) -> Market | None:
        data = await self._get("/markets", {"slug": slug})
        if not data:
            return None
        return Market.model_validate(data[0])

    async def market_by_condition(self, condition_id: str) -> Market | None:
        data = await self._get("/markets", {"condition_ids": condition_id})
        if not data:
            return None
        return Market.model_validate(data[0])

    async def events_by_series(self, series_id: str, limit: int = 30) -> list[Event]:
        """Series siblings, newest end date first (future days, then recent past)."""
        data = await self._get(
            "/events",
            {
                "series_id": series_id,
                "limit": limit,
                "order": "endDate",
                "ascending": "false",
            },
        )
        return [Event.model_validate(e) for e in data]

    async def tags(self) -> list[Tag]:
        data = await self._get("/tags", {"limit": 100, "order": "id"})
        return [Tag.model_validate(t) for t in data]

    async def search(self, query: str, limit_per_type: int = 10) -> list[Event]:
        data = await self._get(
            "/public-search",
            {"q": query, "limit_per_type": limit_per_type, "events_status": "active"},
        )
        events = data.get("events") or []
        return [Event.model_validate(e) for e in events]
