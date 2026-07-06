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

# Window each relative interval spans, for re-anchoring on closed markets.
# ALL is absent on purpose: interval=max works regardless of market state.
WINDOW_SECONDS: dict[str, int] = {
    "1H": 3_600,
    "6H": 21_600,
    "1D": 86_400,
    "1W": 604_800,
    "1M": 2_592_000,
}

# Explicit startTs/endTs queries silently return an empty history past 15
# days per request (verified 2026-07-07) - longer windows must be stitched.
MAX_RANGE_SECONDS = 15 * 86_400


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

    async def prices_history(
        self, token_id: str, interval_key: str = "1D", end_ts: int | None = None
    ) -> list[PricePoint]:
        """Price series for one token.

        `end_ts` re-anchors the relative windows (1H..1M) to that moment
        instead of now - closed markets get their window anchored to the
        close, since interval params are now-relative and come back empty
        once trading stops. ALL ignores it (interval=max spans the full
        lifetime regardless of market state).
        """
        interval, fidelity = INTERVALS.get(interval_key, INTERVALS["1D"])
        window = WINDOW_SECONDS.get(interval_key)
        if end_ts is None or window is None:
            data = await self._get(
                "/prices-history",
                {"market": token_id, "interval": interval, "fidelity": fidelity},
            )
            return [PricePoint.model_validate(p) for p in data.get("history", [])]
        points: list[PricePoint] = []
        seen: set[int] = set()
        start = end_ts - window
        while start < end_ts:
            chunk_end = min(start + MAX_RANGE_SECONDS, end_ts)
            data = await self._get(
                "/prices-history",
                {"market": token_id, "startTs": start, "endTs": chunk_end, "fidelity": fidelity},
            )
            for raw in data.get("history", []):
                point = PricePoint.model_validate(raw)
                if point.t not in seen:  # chunk edges may repeat a sample
                    seen.add(point.t)
                    points.append(point)
            start = chunk_end
        return points
