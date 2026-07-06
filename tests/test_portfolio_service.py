"""PortfolioService caching: TTL, force, invalidation, and the in-flight race.

This cache feeds the order funds/inventory guards - staleness bugs here show
up as wrong balance/position checks on the money path.
"""

from __future__ import annotations

import asyncio

import pytest

from polymarket_tui.core.config import Settings
from polymarket_tui.models.portfolio import Position
from polymarket_tui.services.portfolio import PortfolioService


class FakeData:
    """Counts positions() calls; optionally blocks until released."""

    def __init__(self) -> None:
        self.positions_calls = 0
        self.gate: asyncio.Event | None = None

    async def positions(self, user: str, limit: int = 200) -> list[Position]:
        self.positions_calls += 1
        if self.gate is not None:
            await self.gate.wait()
        return [Position(asset="tok", size=5.0)]

    async def portfolio_value(self, user: str) -> float:
        return 123.0


def make_service(data: FakeData) -> PortfolioService:
    return PortfolioService(Settings(polymarket_funder="0xf"), data, authed=None)


@pytest.mark.asyncio
async def test_second_call_within_ttl_serves_cache():
    data = FakeData()
    svc = make_service(data)
    await svc.positions()
    await svc.positions()
    assert data.positions_calls == 1


@pytest.mark.asyncio
async def test_force_refetches():
    data = FakeData()
    svc = make_service(data)
    await svc.positions()
    await svc.positions(force=True)
    assert data.positions_calls == 2


@pytest.mark.asyncio
async def test_invalidate_refetches():
    data = FakeData()
    svc = make_service(data)
    await svc.positions()
    svc.invalidate()
    await svc.positions()
    assert data.positions_calls == 2


@pytest.mark.asyncio
async def test_concurrent_calls_share_one_fetch():
    """Multiple panes asking at once (startup) must not fan out N fetches."""
    data = FakeData()
    data.gate = asyncio.Event()
    svc = make_service(data)
    tasks = [asyncio.create_task(svc.positions()) for _ in range(3)]
    await asyncio.sleep(0)  # let the first task start its fetch
    data.gate.set()
    results = await asyncio.gather(*tasks)
    assert data.positions_calls == 1
    assert all(len(r) == 1 for r in results)


@pytest.mark.asyncio
async def test_invalidate_during_inflight_fetch_keeps_cache_stale():
    """A fetch already in flight when invalidate() fires may predate the event
    that invalidated (e.g. a fill) - it must not re-stamp a fresh TTL."""
    data = FakeData()
    data.gate = asyncio.Event()
    svc = make_service(data)
    task = asyncio.create_task(svc.positions())
    await asyncio.sleep(0)  # fetch is now in flight
    svc.invalidate()
    data.gate.set()
    await task
    assert data.positions_calls == 1
    data.gate = None
    await svc.positions()  # must refetch: the in-flight result was pre-fill
    assert data.positions_calls == 2


@pytest.mark.asyncio
async def test_no_user_returns_empty_without_fetching():
    data = FakeData()
    svc = PortfolioService(Settings(), data, authed=None)
    assert await svc.positions() == []
    assert data.positions_calls == 0
