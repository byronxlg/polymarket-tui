"""Async client for data-api.polymarket.com (portfolio, activity - keyed by address)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from polymarket_tui.models.market import PricePoint
from polymarket_tui.models.portfolio import ActivityItem, ClosedPosition, Position

BASE_URL = "https://data-api.polymarket.com"
LEADERBOARD_URL = "https://lb-api.polymarket.com"

# /closed-positions silently caps a page at 50 rows: limit=500 returns 50, and
# offset=100 returns another 50. Walk offsets to get more than one page.
CLOSED_PAGE_LIMIT = 50

# How deep the Closed tab reads (3 pages). An active trader's settled history
# runs to hundreds of rows and each page is a round trip; the panes say so
# rather than letting a full page read as the end of the history.
CLOSED_LIMIT = 150


@dataclass(frozen=True)
class ProfileStats:
    """The numbers the web profile header shows. Any field may be None: each
    comes from a different service and a slow one must not blank the others."""

    value: float | None = None  # current positions value
    profit: float | None = None  # all-time realized + unrealized
    volume: float | None = None  # all-time traded volume
    markets_traded: int | None = None


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

    async def closed_positions(
        self, user: str, limit: int = CLOSED_LIMIT
    ) -> list[ClosedPosition]:
        """Settled positions, most recently closed first.

        sortBy accepts only [REALIZEDPNL AVGPRICE PRICE TITLE TIMESTAMP]; the
        default is REALIZEDPNL (biggest wins first), which reads as a highlight
        reel rather than a history, so ask for TIMESTAMP.
        """
        out: list[ClosedPosition] = []
        offset = 0
        while len(out) < limit:
            page = await self._get(
                "/closed-positions",
                {
                    "user": user,
                    "limit": min(CLOSED_PAGE_LIMIT, limit - len(out)),
                    "offset": offset,
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "DESC",
                },
            )
            if not page:
                break
            out.extend(ClosedPosition.model_validate(p) for p in page)
            if len(page) < CLOSED_PAGE_LIMIT:
                break  # short page - that was the last one
            offset += len(page)
        return out

    async def portfolio_value(self, user: str) -> float | None:
        data = await self._get("/value", {"user": user})
        if isinstance(data, list) and data:
            return float(data[0].get("value", 0.0))
        return None

    async def markets_traded(self, user: str) -> int | None:
        data = await self._get("/traded", {"user": user})
        if isinstance(data, dict) and "traded" in data:
            return int(data["traded"])
        return None

    async def _leaderboard_amount(self, path: str, user: str) -> float | None:
        """lb-api /volume and /profit both answer [{proxyWallet, amount, ...}]
        when filtered to one address, and [] for an address that never traded."""
        resp = await self._http.get(
            f"{LEADERBOARD_URL}{path}", params={"window": "all", "limit": 1, "address": user}
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return float(data[0].get("amount", 0.0))
        return None

    async def profile_stats(self, user: str) -> ProfileStats:
        """The profile header numbers, gathered concurrently across three hosts.
        A field whose service errors comes back None rather than sinking the row."""
        value, profit, volume, traded = await asyncio.gather(
            self.portfolio_value(user),
            self._leaderboard_amount("/profit", user),
            self._leaderboard_amount("/volume", user),
            self.markets_traded(user),
            return_exceptions=True,
        )

        def ok(result: Any) -> Any:
            return None if isinstance(result, BaseException) else result

        return ProfileStats(
            value=ok(value), profit=ok(profit), volume=ok(volume), markets_traded=ok(traded)
        )

    async def market_trades(self, condition_id: str, limit: int = 30) -> list[ActivityItem]:
        """Public recent trades for one market (the web UI's activity tab)."""
        data = await self._get("/trades", {"market": condition_id, "limit": limit})
        return [ActivityItem.model_validate(t) for t in data]

    async def user_pnl(self, user: str, interval: str = "1m") -> list[PricePoint]:
        """Cumulative profit history from the pnl service (absolute URL, other host)."""
        resp = await self._http.get(
            "https://user-pnl-api.polymarket.com/user-pnl",
            params={"user_address": user, "interval": interval, "fidelity": "1d"},
        )
        resp.raise_for_status()
        data = resp.json()
        return [PricePoint.model_validate(p) for p in data if isinstance(p, dict)]

    async def activity(self, user: str, limit: int = 100) -> list[ActivityItem]:
        data = await self._get("/activity", {"user": user, "limit": limit})
        return [ActivityItem.model_validate(a) for a in data]
