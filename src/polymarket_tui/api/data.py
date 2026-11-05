"""Async client for data-api.polymarket.com/v2 (portfolio, activity - keyed by address).

v1, lb-api and user-pnl-api are retired (410). docs/api-reference.md has the shapes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from polymarket_tui.models.market import PricePoint
from polymarket_tui.models.portfolio import ActivityItem, ClosedPosition, Position

BASE_URL = "https://data-api.polymarket.com/v2"

# How deep the Closed tab reads. An active trader's settled history runs to
# hundreds of rows; the panes say so rather than letting a full page read as
# the end of the history.
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
        """The payload of v2's {data, pagination} envelope. A documented miss is
        data: null or an empty list, not an error."""
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json().get("data")

    async def positions(self, user: str, limit: int = 200) -> list[Position]:
        """Open positions. OPEN is v2's superset: it includes unredeemed winners,
        but not resolved losers (REDEEMABLE_LOST), which the app hides anyway.
        Archived markets are asked for because their winners still pay out."""
        data = await self._get(
            "/positions",
            {"user": user, "limit": limit, "sort_by": "CURRENT_VALUE", "include_archived": "true"},
        )
        return [Position.model_validate(p) for p in data or []]

    async def closed_positions(self, user: str, limit: int = CLOSED_LIMIT) -> list[ClosedPosition]:
        """Exited positions, most recently closed first. The default order is
        REALIZED_PNL, which reads as a highlight reel rather than a history."""
        page = await self._get(
            "/positions",
            {
                "user": user,
                "status": "CLOSED",
                "limit": limit,
                "sort_by": "TIMESTAMP",
                "sort_direction": "DESC",
            },
        )
        out: list[ClosedPosition] = []
        seen: set[tuple[str, str]] = set()
        for raw in page or []:
            pos = ClosedPosition.model_validate(raw)
            # The table keys rows on exactly this pair, and a repeat is a
            # DuplicateKey crash, so the server's word is not taken for it.
            key = (pos.slug, pos.asset)
            if key not in seen:
                seen.add(key)
                out.append(pos)
        return out

    async def portfolio_value(self, user: str) -> float | None:
        data = await self._get("/value", {"user": user})
        if isinstance(data, dict) and data.get("value") is not None:
            return float(data["value"])
        return None

    async def markets_traded(self, user: str) -> int | None:
        """/v2/user-stats `trades` counts distinct markets, not individual trades."""
        data = await self._get("/user-stats", {"user": user})
        if isinstance(data, dict) and data.get("trades") is not None:
            return int(data["trades"])
        return None

    async def _all_time_standing(self, user: str) -> tuple[float | None, float | None]:
        """(profit, volume). With `user` the board answers one object, not a page."""
        data = await self._get("/leaderboard", {"user": user, "time_period": "all"})
        if not isinstance(data, dict):
            return None, None
        return data.get("pnl"), data.get("volume")

    async def profile_stats(self, user: str) -> ProfileStats:
        """The profile header numbers, gathered concurrently across three routes.
        A field whose route errors comes back None rather than sinking the row."""
        value, standing, traded = await asyncio.gather(
            self.portfolio_value(user),
            self._all_time_standing(user),
            self.markets_traded(user),
            return_exceptions=True,
        )

        def ok(result: Any) -> Any:
            return None if isinstance(result, BaseException) else result

        profit, volume = ok(standing) or (None, None)
        return ProfileStats(
            value=ok(value), profit=profit, volume=volume, markets_traded=ok(traded)
        )

    async def market_trades(self, condition_id: str, limit: int = 30) -> list[ActivityItem]:
        """Public recent trades for one market (the web UI's activity tab)."""
        data = await self._get("/trades", {"condition": condition_id, "limit": limit})
        return [ActivityItem.model_validate(t) for t in data or []]

    async def user_pnl(self, user: str, interval: str = "1m") -> list[PricePoint]:
        """Cumulative profit history. position_pnl is realized plus unrealized,
        the figure the old pnl service and the profile header both mean."""
        data = await self._get("/user-pnl", {"user": user, "interval": interval, "fidelity": "1d"})
        points = (data or {}).get("points") or []
        return [
            PricePoint(t=p["timestamp"], p=p["position_pnl"])
            for p in points
            if p.get("position_pnl") is not None
        ]

    async def activity(self, user: str, limit: int = 100) -> list[ActivityItem]:
        data = await self._get("/activity", {"user": user, "limit": limit})
        return [ActivityItem.model_validate(a) for a in data or []]
