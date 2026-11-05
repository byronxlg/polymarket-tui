"""data-api v2 shapes, off real responses (2026-11-05), and the live contract.

v1 went 410 and nothing said so: the panes swallow fetch errors and every mocked
test kept passing. test_live_contract is the check that would have caught it. It
is marked `live`, stays out of the normal run, and runs daily in api-contract.yml.
"""

from __future__ import annotations

import httpx
import pytest

from polymarket_tui.api.data import BASE_URL, DataApiClient
from polymarket_tui.models.portfolio import ActivityItem, Position

POSITION = {
    "proxy_wallet": "0xafd26fec8dd53547af5abc2b64d9492db4e1a9e9",
    "token_id": "27506633603111896292511900943419994727225522835567073486736117870219377801649",
    "condition_id": "0xadd1995ef49223fd953b3d7db29d6e4dafa7c1d4ad07abe7b537fb4df55ec990",
    "current_size": 5.0,
    "avg_price": 0.997,
    "entry_cost_usdc": 4.985,
    "total_cost_usdc": 4.985,
    "current_price": 0.9995,
    "current_value": 4.9975,
    "total_size": 5.0,
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.0125,
    "percent_pnl": 0.2507,
    "status": "OPEN",
    "redeemable": False,
    "title": "Counter-Strike: TheChampionGG vs SANCTUM - Map 1 Winner",
    "slug": "cs2-thecha-snctm-2026-11-05-game1",
    "event_slug": "cs2-thecha-snctm-2026-11-05",
    "outcome": "SANCTUM",
    "outcome_index": 1,
    "end_date": "2026-11-05",
}

TRADE = {
    "proxy_wallet": "0xafd26fec8dd53547af5abc2b64d9492db4e1a9e9",
    "side": "BUY",
    "token_id": "61461785089231839643287655992285720821164560378443604184819151676568549975561",
    "condition_id": "0x4e89e7892da14b1e15c4030d9cd85e87aea91420fca4c32045f782746afb94b8",
    "size": 5.0,
    "price": 0.999,
    "timestamp": 1793902113,
    "title": "Counter-Strike: PENSIONERS vs PARTIZAN (BO1)",
    "slug": "cs2-pensio-prtzn-2026-11-05",
    "event_slug": "cs2-pensio-prtzn-2026-11-05",
    "outcome": "PARTIZAN",
    "outcome_index": 1,
    "name": "Felipe001",
    "pseudonym": "Aged-Overload",
}


def _client(handler) -> DataApiClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    return DataApiClient(http)


def test_position_maps_the_fields_the_money_path_reads() -> None:
    pos = Position.model_validate(POSITION)
    # size is what the sell guard and the cash-out prefill compare against.
    assert pos.size == 5.0
    assert pos.asset == POSITION["token_id"]
    assert pos.cur_price == 0.9995
    assert pos.initial_value == 4.985
    assert pos.cash_pnl == 0.0125
    assert pos.percent_pnl == 0.2507
    assert pos.event_slug == "cs2-thecha-snctm-2026-11-05"


def test_one_null_amount_does_not_lose_the_row() -> None:
    assert Position.model_validate({**POSITION, "unrealized_pnl": None}).cash_pnl == 0.0


def test_trade_derives_usdc_because_the_feed_omits_it() -> None:
    item = ActivityItem.model_validate(TRADE)
    assert item.usdc_size == pytest.approx(4.995)
    assert item.proxy_wallet.startswith("0xafd2")
    assert item.trader == "Felipe001"


@pytest.mark.asyncio
async def test_positions_unwraps_the_envelope_and_asks_for_archived_winners() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [POSITION], "pagination": {}})

    out = await _client(handler).positions("0xf")
    assert [p.size for p in out] == [5.0]
    assert seen[0].url.path == "/v2/positions"
    assert seen[0].url.params["include_archived"] == "true"
    assert seen[0].url.params["sort_by"] == "CURRENT_VALUE"


@pytest.mark.asyncio
async def test_market_trades_filters_by_condition() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [TRADE]})

    assert len(await _client(handler).market_trades("0xabc")) == 1
    assert seen[0].url.path == "/v2/trades"
    assert seen[0].url.params["condition"] == "0xabc"


@pytest.mark.asyncio
async def test_user_pnl_reads_points_and_skips_an_unavailable_one() -> None:
    body = {
        "data": {
            "points": [
                {"timestamp": 100, "position_pnl": -5.5},
                {"timestamp": 200, "position_pnl": None},
            ]
        }
    }
    out = await _client(lambda _: httpx.Response(200, json=body)).user_pnl("0xf")
    assert [(p.t, p.p) for p in out] == [(100, -5.5)]


@pytest.mark.asyncio
async def test_a_retired_route_raises_rather_than_reading_as_empty() -> None:
    client = _client(lambda _: httpx.Response(410, json={"error": "retired"}))
    with pytest.raises(httpx.HTTPStatusError):
        await client.positions("0xf")


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_contract() -> None:
    """Every read the app makes, against the real API, for an active wallet off
    the live feed: each route answers, and parsed rows carry the fields we use.
    A rename that parses to a default is the failure mode, so values are checked."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as http:
        client = DataApiClient(http)
        feed = (await http.get("/trades", params={"limit": 1})).raise_for_status().json()["data"]
        condition, wallet = feed[0]["condition_id"], feed[0]["proxy_wallet"]

        trades = await client.market_trades(condition, limit=5)
        assert trades and all(t.size > 0 and t.proxy_wallet and t.asset for t in trades)

        open_rows = await client.positions(wallet, limit=20)
        assert all(p.asset and p.condition_id and p.size > 0 for p in open_rows)

        closed = await client.closed_positions(wallet, limit=20)
        assert all(c.asset and c.timestamp for c in closed)

        activity = await client.activity(wallet, limit=5)
        assert activity and all(a.type and a.timestamp for a in activity)

        assert await client.portfolio_value(wallet) is not None
        stats = await client.profile_stats(wallet)
        assert stats.markets_traded is not None
        assert stats.volume is not None and stats.profit is not None

        pnl = await client.user_pnl(wallet)
        assert pnl and all(p.t for p in pnl)
