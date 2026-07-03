"""Async client for CLOB public REST reads (no auth needed for books/prices/history)."""

from __future__ import annotations

from typing import Any

import httpx

from polymarket_tui.models.market import OrderBook, PricePoint

BASE_URL = "https://clob.polymarket.com"

# Chart interval -> (API interval param, fidelity in minutes)
INTERVALS: dict[str, tuple[str, int]] = {
    "1H": ("1h", 1),
    "6H": ("6h", 10),
    "1D": ("1d", 60),
    "1W": ("1w", 360),
    "1M": ("1m", 1440),
    "ALL": ("max", 1440),
}


class ClobPublicClient:
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

    async def order_book(self, token_id: str) -> OrderBook:
        data = await self._get("/book", {"token_id": token_id})
        return OrderBook.model_validate(data)

    async def prices_history(self, token_id: str, interval_key: str = "1D") -> list[PricePoint]:
        interval, fidelity = INTERVALS.get(interval_key, INTERVALS["1D"])
        data = await self._get(
            "/prices-history",
            {"market": token_id, "interval": interval, "fidelity": fidelity},
        )
        return [PricePoint.model_validate(p) for p in data.get("history", [])]
