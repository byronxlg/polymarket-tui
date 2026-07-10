"""Home sort: "ending soonest" must ask Gamma for a live-only window.

Gamma leaves long-expired events flagged active/closed=false - over 1000 of
them on 2026-07-10, all sorting ahead of anything live under endDate ascending.
The home pane drops ended events client-side, so without a server-side
end_date_min the whole page filters away and the list renders empty (#133).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from textual.app import App, ComposeResult

from polymarket_tui.api.gamma import GammaClient
from polymarket_tui.models.market import Event
from polymarket_tui.state import cache
from polymarket_tui.ui.screens.home import SORT_ORDERS, HomePane

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _event(slug: str, end: datetime | None) -> Event:
    return Event.model_validate(
        {
            "id": slug,
            "slug": slug,
            "title": slug,
            "endDate": end.isoformat() if end else None,
            "markets": [
                {
                    "id": f"{slug}-m",
                    "slug": slug,
                    "question": slug,
                    "conditionId": f"0x{slug}",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.5", "0.5"]',
                    "clobTokenIds": '["1", "2"]',
                }
            ],
        }
    )


class _StubGamma:
    """Records the kwargs of every events() call; serves live events."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def events(self, **kwargs) -> list[Event]:
        self.calls.append(kwargs)
        return [_event(f"live-{i}", NOW + timedelta(days=i + 1)) for i in range(3)]


class _StubPortfolio:
    async def flag_slugs(self, events):
        return set(), set()


class _StubWatchlist:
    slugs: list[str] = []


class _HomeApp(App):
    def __init__(self, gamma: _StubGamma) -> None:
        super().__init__()
        self.gamma = gamma
        self.portfolio = _StubPortfolio()
        self.watchlist = _StubWatchlist()

    def compose(self) -> ComposeResult:
        yield HomePane()


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")


async def _load_once(sort: str) -> list[dict]:
    """Mount HomePane, load under `sort`, return the kwargs of every fetch."""
    gamma = _StubGamma()
    app = _HomeApp(gamma)
    async with app.run_test() as pilot:
        pane = app.query_one(HomePane)
        pane._sort_index = SORT_ORDERS.index(sort)
        pane.load_events()
        # The worker is exclusive+async: let it finish before asserting.
        await app.workers.wait_for_complete()
        await pilot.pause()
    return gamma.calls


async def test_ending_soonest_sends_a_server_side_cutoff() -> None:
    # Without end_date_min every row Gamma returns is long expired, the
    # ended-events filter drops them all, and the table renders empty.
    before = datetime.now(UTC)
    load = (await _load_once("endDate"))[-1]
    after = datetime.now(UTC)
    assert load["order"] == "endDate"
    assert load["ascending"] is True
    # The window opens at "now", so it holds exactly the events still running.
    assert load["end_date_min"] is not None
    assert before <= load["end_date_min"] <= after


@pytest.mark.parametrize("sort", ["volume24hr", "liquidity", "startDate"])
async def test_other_sorts_send_no_cutoff(sort: str) -> None:
    # end_date_min also excludes dateless events (World Cup props etc.), so it
    # must not leak onto sorts where the end date is not the key.
    assert (await _load_once(sort))[-1]["end_date_min"] is None


async def test_cutoff_is_pinned_across_pages() -> None:
    # Recomputing the cutoff per page would shift Gamma's offsets as markets
    # expire mid-browse (5m crypto events sit at the head of this list), so an
    # appended page would silently skip rows.
    gamma = _StubGamma()
    app = _HomeApp(gamma)
    async with app.run_test() as pilot:
        pane = app.query_one(HomePane)
        pane._sort_index = SORT_ORDERS.index("endDate")
        pane.load_events()
        await app.workers.wait_for_complete()
        await pilot.pause()
        pane.load_events(append=True)
        await app.workers.wait_for_complete()
        await pilot.pause()

    fresh, appended = gamma.calls[-2], gamma.calls[-1]
    assert appended["offset"] > fresh["offset"]  # really the next page
    assert appended["end_date_min"] == fresh["end_date_min"]


async def test_gamma_client_serialises_end_date_min() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=[])

    http = httpx.AsyncClient(
        base_url="https://gamma.test", transport=httpx.MockTransport(handler)
    )
    client = GammaClient(http)
    await client.events(order="endDate", ascending=True, end_date_min=NOW)
    assert seen["end_date_min"] == NOW.isoformat()

    seen.clear()
    await client.events(order="volume24hr")
    assert "end_date_min" not in seen
