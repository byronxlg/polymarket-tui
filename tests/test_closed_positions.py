"""Closed positions: the settled half of a profile (Active | Closed).

data-api serves these from /closed-positions with a different shape than
/positions - no size (the shares are gone), realized P&L instead of a mark, and
no percentage - and it silently caps a page at 50 rows. A client that trusts
its own `limit` shows a truncated history and calls it complete.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from polymarket_tui.api.data import BASE_URL, CLOSED_LIMIT, CLOSED_PAGE_LIMIT, DataApiClient
from polymarket_tui.core.links import market_url
from polymarket_tui.models.portfolio import ClosedPosition
from polymarket_tui.ui.theme import DOWN, UP
from polymarket_tui.ui.tiers import columns_need, effective_tier
from polymarket_tui.ui.widgets.closed_table import ClosedTable
from polymarket_tui.ui.widgets.tables import (
    CLOSED_SPACIOUS_TIER_COLUMNS,
    CLOSED_TIER_COLUMNS,
    closed_meta,
    closed_row,
)

# A real /closed-positions record (wettor-bettor-b, 2026-07-10). Note endDate
# carries a full timestamp here while /positions sends a bare date.
RAW = {
    "proxyWallet": "0x20118f14091ee38afa401ee89e7b8343e6c8845b",
    "asset": "57295447409380755776069872216650648586165601801513220125339658071871455932443",
    "conditionId": "0x289f4797323bc8dfa3b1dcddc80410aa358f8a34336a550c7afbad32f5915da3",
    "avgPrice": 0.543042,
    "totalBought": 560.144189,
    "realizedPnl": 250.357573,
    "curPrice": 1,
    "title": "Will the highest temperature in Wellington be 16°C on June 6?",
    "slug": "highest-temperature-in-wellington-on-june-6-2026-16c",
    "eventSlug": "highest-temperature-in-wellington-on-june-6-2026",
    "outcome": "No",
    "outcomeIndex": 1,
    "endDate": "2026-06-06T00:00:00Z",
    "timestamp": 1780702263,
}


def _raw(i: int, **over) -> dict:
    stamp = RAW["timestamp"] - i
    return {**RAW, "asset": str(i), "slug": f"market-{i}", "timestamp": stamp, **over}


def _cell(pos: ClosedPosition, key: str):
    """The rendered cell under `key` of the full condensed row."""
    spec = CLOSED_TIER_COLUMNS["full"]
    return closed_row(pos)[[k for k, _, _ in spec].index(key)]


# -- model ---------------------------------------------------------------


def test_parses_the_live_payload() -> None:
    pos = ClosedPosition.model_validate(RAW)
    assert pos.total_bought == pytest.approx(560.144189)
    assert pos.realized_pnl == pytest.approx(250.357573)
    assert pos.condition_id.startswith("0x289f")
    assert pos.event_slug == "highest-temperature-in-wellington-on-june-6-2026"
    assert pos.end_date == datetime(2026, 6, 6, tzinfo=UTC)


def test_percent_pnl_is_return_on_cost() -> None:
    # The endpoint sends no percentage; it is realized against what went in.
    pos = ClosedPosition(totalBought=200.0, realizedPnl=50.0)
    assert pos.percent_pnl == pytest.approx(25.0)


def test_percent_pnl_of_a_zero_cost_position_is_zero_not_a_crash() -> None:
    assert ClosedPosition(totalBought=0.0, realizedPnl=0.0).percent_pnl == 0.0


def test_closed_at_reads_the_timestamp() -> None:
    assert ClosedPosition.model_validate(RAW).closed_at == datetime.fromtimestamp(
        RAW["timestamp"], tz=UTC
    )
    assert ClosedPosition(timestamp=0).closed_at is None


# -- client paging -------------------------------------------------------


def _client(pages: dict[int, int]) -> tuple[DataApiClient, list[httpx.Request]]:
    """Serve `pages[offset]` rows for each offset; record every request."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", CLOSED_PAGE_LIMIT))
        rows = min(pages.get(offset, 0), limit)
        return httpx.Response(200, json=[_raw(offset + i) for i in range(rows)])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    return DataApiClient(http), seen


@pytest.mark.asyncio
async def test_walks_offsets_past_the_fifty_row_page_cap() -> None:
    # 107 settled positions: the server hands back 50, 50, then 7.
    client, seen = _client({0: 50, 50: 50, 100: 7})
    out = await client.closed_positions("0xf", limit=150)
    assert len(out) == 107
    assert [int(r.url.params["offset"]) for r in seen] == [0, 50, 100]


@pytest.mark.asyncio
async def test_a_short_first_page_ends_the_walk() -> None:
    client, seen = _client({0: 12})
    assert len(await client.closed_positions("0xf", limit=150)) == 12
    assert len(seen) == 1  # no speculative second request


@pytest.mark.asyncio
async def test_an_empty_history_makes_one_request() -> None:
    client, seen = _client({})
    assert await client.closed_positions("0xf") == []
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_limit_is_honoured_across_pages() -> None:
    client, seen = _client({0: 50, 50: 50})
    out = await client.closed_positions("0xf", limit=60)
    assert len(out) == 60
    # Second page asks for only the 10 rows still wanted, not another 50.
    assert [int(r.url.params["limit"]) for r in seen] == [50, 10]


@pytest.mark.asyncio
async def test_a_deeper_history_than_the_cap_comes_back_exactly_full() -> None:
    # The panes decide whether to say "showing the N most recently closed" by
    # comparing len(rows) to CLOSED_LIMIT, so a truncated read must fill it
    # exactly - never overshoot, never come up one short.
    client, _ = _client({0: 50, 50: 50, 100: 50, 150: 50})
    assert len(await client.closed_positions("0xf", limit=CLOSED_LIMIT)) == CLOSED_LIMIT


@pytest.mark.asyncio
async def test_asks_for_most_recently_closed_first() -> None:
    # The endpoint's default sort is REALIZEDPNL - a highlight reel, not a
    # history. Closed is a history, so it must ask for TIMESTAMP DESC.
    client, seen = _client({0: 3})
    await client.closed_positions("0xf")
    assert seen[0].url.params["sortBy"] == "TIMESTAMP"
    assert seen[0].url.params["sortDirection"] == "DESC"


# -- profile stats -------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_stats_survives_one_dead_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "lb-api" in request.url.host:
            return httpx.Response(503)  # leaderboard down
        if request.url.path == "/value":
            return httpx.Response(200, json=[{"value": 398.48}])
        return httpx.Response(200, json={"traded": 339})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    stats = await DataApiClient(http).profile_stats("0xf")
    assert stats.value == pytest.approx(398.48)
    assert stats.markets_traded == 339
    assert stats.profit is None and stats.volume is None  # dropped, not fatal


# -- rows ----------------------------------------------------------------


def test_row_has_one_cell_per_column_at_every_tier() -> None:
    pos = ClosedPosition.model_validate(RAW)
    for columns in (CLOSED_TIER_COLUMNS, CLOSED_SPACIOUS_TIER_COLUMNS):
        for tier, spec in columns.items():
            density = "spacious" if columns is CLOSED_SPACIOUS_TIER_COLUMNS else "condensed"
            assert len(closed_row(pos, tier=tier, density=density)) == len(spec)


def test_realized_pnl_carries_the_sign_colour() -> None:
    win = _cell(ClosedPosition(totalBought=100.0, realizedPnl=25.0), "realized")
    loss = _cell(ClosedPosition(totalBought=100.0, realizedPnl=-25.0), "realized")
    assert win.style == UP and "+25.00" in win.plain and "+25%" in win.plain
    assert loss.style == DOWN and "-25.00" in loss.plain and "-25%" in loss.plain


def test_a_settled_winner_states_the_pnl_and_draws_no_verdict() -> None:
    # cur_price 1 means held to resolution, but a position sold out early
    # prices mid - the row must never editorialise "won"/"lost".
    row = closed_row(ClosedPosition.model_validate(RAW))
    text = " ".join(cell.plain if hasattr(cell, "plain") else str(cell) for cell in row)
    assert "won" not in text.lower() and "lost" not in text.lower()
    assert "+250.36" in text


def test_spacious_meta_line_states_outcome_avg_and_close_date() -> None:
    meta = closed_meta(ClosedPosition.model_validate(RAW))
    assert meta.startswith("No · avg 54.3c · closed ")


# -- open on web ---------------------------------------------------------


def test_web_url_prefers_the_event_slug() -> None:
    # Gamma delists a resolved market (both /markets?slug= and ?condition_ids=
    # answer []), so the web page is the only place a closed position's market
    # still exists. The event page is the canonical 200.
    pos = ClosedPosition.model_validate(RAW)
    assert market_url(pos.event_slug, pos.slug) == (
        "https://polymarket.com/event/highest-temperature-in-wellington-on-june-6-2026"
    )


def test_open_and_copy_reports_only_what_landed(monkeypatch: pytest.MonkeyPatch) -> None:
    import polymarket_tui.core.links as links

    monkeypatch.setattr(links, "open_in_browser", lambda url: True)
    monkeypatch.setattr(links, "copy_to_clipboard", lambda url: True)
    assert links.open_and_copy("http://x") == "Opened http://x  (copied)"

    monkeypatch.setattr(links, "open_in_browser", lambda url: False)
    assert links.open_and_copy("http://x") == "Copied http://x"

    monkeypatch.setattr(links, "copy_to_clipboard", lambda url: False)
    assert links.open_and_copy("http://x") == "URL http://x"


def test_closed_table_hides_the_open_hint_when_empty() -> None:
    table = ClosedTable()
    assert table.check_action("open_on_web", ()) is False  # no rows, nothing to open


# -- tiers ---------------------------------------------------------------


def test_narrow_panes_drop_columns_rather_than_clip() -> None:
    # A compact (30% parent) pane must still fit its column set.
    compact_width = columns_need(CLOSED_TIER_COLUMNS["compact"])
    assert effective_tier("full", compact_width, CLOSED_TIER_COLUMNS) == "compact"
    full_width = columns_need(CLOSED_TIER_COLUMNS["full"])
    assert effective_tier("full", full_width, CLOSED_TIER_COLUMNS) == "full"
    # Tiers shrink monotonically, so a wider set never hides inside a narrower.
    needs = [columns_need(CLOSED_TIER_COLUMNS[t]) for t in ("compact", "medium", "full")]
    assert needs == sorted(needs)
