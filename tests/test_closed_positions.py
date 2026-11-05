"""Closed positions: the settled half of a profile (Active | Closed).

data-api v2 serves these from /positions?status=CLOSED: the same route as open
positions, but the shares are gone, so the money is realized P&L rather than a
mark, and the default order is biggest win rather than most recent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from polymarket_tui.api.data import BASE_URL, CLOSED_LIMIT, DataApiClient
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

# A real /v2/positions?status=CLOSED record, 2026-11-05. Note total_cost_usdc is
# only the fees by now, and percent_pnl is 0: the return is percent_realized_pnl.
RAW = {
    "proxy_wallet": "0xafd26fec8dd53547af5abc2b64d9492db4e1a9e9",
    "token_id": "24284034030654287997033489800446777667354760444381473294763283411133277982539",
    "condition_id": "0x885e8eff6428727c847afad007ac5ba620a3cf8ff11db532c2dfa8a2d14a19db",
    "current_size": 0.0,
    "avg_price": 0.4111,
    "entry_cost_usdc": 0.0,
    "total_cost_usdc": 0.77485,
    "current_price": 1.0,
    "current_value": 0.0,
    "total_size": 133.9926,
    "realized_pnl": 78.9015,
    "unrealized_pnl": 0.0,
    "percent_pnl": 0.0,
    "percent_realized_pnl": 143.2203,
    "status": "CLOSED",
    "title": "Bitcoin Up or Down - September 9, 8:20PM-8:25PM ET",
    "slug": "btc-updown-5m-1788999600",
    "event_slug": "btc-updown-5m-1788999600",
    "outcome": "Up",
    "outcome_index": 0,
    "end_date": "2026-09-10",
    "last_event_at": 1789000543,
}


def _raw(i: int, **over) -> dict:
    stamp = RAW["last_event_at"] - i
    return {**RAW, "token_id": str(i), "slug": f"market-{i}", "last_event_at": stamp, **over}


def _cell(pos: ClosedPosition, key: str):
    """The rendered cell under `key` of the full condensed row."""
    spec = CLOSED_TIER_COLUMNS["full"]
    return closed_row(pos)[[k for k, _, _ in spec].index(key)]


# -- model ---------------------------------------------------------------


def test_parses_the_live_payload() -> None:
    pos = ClosedPosition.model_validate(RAW)
    assert pos.realized_pnl == pytest.approx(78.9015)
    assert pos.condition_id.startswith("0x885e")
    assert pos.asset == RAW["token_id"]
    assert pos.cur_price == 1.0
    assert pos.end_date == datetime(2026, 9, 10)  # v2 sends a bare date


def test_percent_is_the_servers_return_on_cost_not_the_open_positions_field() -> None:
    assert ClosedPosition.model_validate(RAW).percent_pnl == pytest.approx(143.2203)


def test_cost_is_what_went_in_not_the_fees() -> None:
    # realized / cost must agree with the server's percentage, or the Cost
    # column and the % beside it describe different positions.
    pos = ClosedPosition.model_validate(RAW)
    assert pos.total_bought == pytest.approx(55.08, abs=0.01)
    assert pos.realized_pnl / pos.total_bought * 100 == pytest.approx(143.2, abs=0.1)


def test_a_null_amount_means_unavailable_and_keeps_the_row() -> None:
    pos = ClosedPosition.model_validate({**RAW, "percent_realized_pnl": None})
    assert pos.percent_pnl == 0.0


def test_closed_at_reads_the_timestamp() -> None:
    assert ClosedPosition.model_validate(RAW).closed_at == datetime.fromtimestamp(
        RAW["last_event_at"], tz=UTC
    )
    assert ClosedPosition(timestamp=0).closed_at is None


# -- client --------------------------------------------------------------


def _client(rows: list[dict]) -> tuple[DataApiClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": rows, "pagination": {"has_more": False}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    return DataApiClient(http), seen


@pytest.mark.asyncio
async def test_asks_for_closed_most_recent_first_up_to_the_limit() -> None:
    # The default sort is REALIZED_PNL - a highlight reel, not a history.
    client, seen = _client([_raw(0)])
    await client.closed_positions("0xf")
    params = seen[0].url.params
    assert seen[0].url.path == "/v2/positions"
    assert params["status"] == "CLOSED"
    assert params["sort_by"] == "TIMESTAMP"
    assert params["sort_direction"] == "DESC"
    assert int(params["limit"]) == CLOSED_LIMIT


@pytest.mark.asyncio
async def test_a_repeated_row_is_not_duplicated() -> None:
    # The table keys rows on slug|asset; a repeat is a DuplicateKey crash.
    client, _ = _client([_raw(0), _raw(1), _raw(0)])
    keys = [(p.slug, p.asset) for p in await client.closed_positions("0xf")]
    assert len(keys) == 2 and len(set(keys)) == 2


@pytest.mark.asyncio
async def test_an_empty_history_and_a_null_payload_are_both_empty() -> None:
    assert await _client([])[0].closed_positions("0xf") == []
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": None})),
        base_url=BASE_URL,
    )
    assert await DataApiClient(http).closed_positions("0xf") == []


# -- profile stats -------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_stats_survives_one_dead_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/leaderboard":
            return httpx.Response(503)
        if request.url.path == "/v2/value":
            return httpx.Response(200, json={"data": {"value": 398.48}})
        return httpx.Response(200, json={"data": {"trades": 339}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    stats = await DataApiClient(http).profile_stats("0xf")
    assert stats.value == pytest.approx(398.48)
    assert stats.markets_traded == 339
    assert stats.profit is None and stats.volume is None  # dropped, not fatal


@pytest.mark.asyncio
async def test_profile_stats_reads_the_all_time_standing() -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = request
        return httpx.Response(200, json={"data": {"pnl": -212.5, "volume": 20078.6, "value": 1.0}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    stats = await DataApiClient(http).profile_stats("0xf")
    assert stats.profit == pytest.approx(-212.5)
    assert stats.volume == pytest.approx(20078.6)
    # The board defaults to `day`; the header says all-time.
    assert seen["/v2/leaderboard"].url.params["time_period"] == "all"


# -- rows ----------------------------------------------------------------


def test_row_has_one_cell_per_column_at_every_tier() -> None:
    pos = ClosedPosition.model_validate(RAW)
    for columns in (CLOSED_TIER_COLUMNS, CLOSED_SPACIOUS_TIER_COLUMNS):
        for tier, spec in columns.items():
            density = "spacious" if columns is CLOSED_SPACIOUS_TIER_COLUMNS else "condensed"
            assert len(closed_row(pos, tier=tier, density=density)) == len(spec)


def test_realized_pnl_carries_the_sign_colour() -> None:
    win = _cell(ClosedPosition(realized_pnl=25.0, percent_pnl=25.0), "realized")
    loss = _cell(ClosedPosition(realized_pnl=-25.0, percent_pnl=-25.0), "realized")
    assert win.style == UP and "+25.00" in win.plain and "+25%" in win.plain
    assert loss.style == DOWN and "-25.00" in loss.plain and "-25%" in loss.plain


def test_a_settled_winner_states_the_pnl_and_draws_no_verdict() -> None:
    # cur_price 1 means held to resolution, but a position sold out early
    # prices mid - the row must never editorialise "won"/"lost".
    row = closed_row(ClosedPosition.model_validate(RAW))
    text = " ".join(cell.plain if hasattr(cell, "plain") else str(cell) for cell in row)
    assert "won" not in text.lower() and "lost" not in text.lower()
    assert "+78.90" in text


def test_spacious_meta_line_states_outcome_avg_and_close_date() -> None:
    meta = closed_meta(ClosedPosition.model_validate(RAW))
    assert meta.startswith("Up · avg 41.1c · closed ")


# -- open on web ---------------------------------------------------------


def test_web_url_prefers_the_event_slug() -> None:
    # Gamma delists a resolved market (both /markets?slug= and ?condition_ids=
    # answer []), so the web page is the only place a closed position's market
    # still exists. The event page is the canonical 200.
    pos = ClosedPosition.model_validate(RAW)
    assert market_url(pos.event_slug, pos.slug) == (
        "https://polymarket.com/event/btc-updown-5m-1788999600"
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
