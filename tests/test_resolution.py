"""Closed-market resolution: model fields, status tokens, anchored history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from polymarket_tui.api.clob import MAX_RANGE_SECONDS, ClobPublicClient
from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market

CLOSE_TS = 1730906261  # 2024-11-06 15:17:41+00


def closed_market(**overrides) -> Market:
    payload = {
        "question": "Will it happen?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["1", "0"]',
        "closed": True,
        "closedTime": "2024-11-06 15:17:41+00",
        "umaResolutionStatus": "resolved",
        "endDate": "2024-11-05T12:00:00Z",
    }
    payload.update(overrides)
    return Market.model_validate(payload)


# -- model fields -------------------------------------------------------------


def test_closed_time_parses_postgres_offset():
    m = closed_market()
    assert m.closed_time == datetime(2024, 11, 6, 15, 17, 41, tzinfo=UTC)
    assert m.uma_resolution_status == "resolved"


def test_closed_time_none_and_iso_still_parse():
    assert closed_market(closedTime=None).closed_time is None
    iso = closed_market(closedTime="2024-11-06T15:17:41Z")
    assert iso.closed_time == datetime(2024, 11, 6, 15, 17, 41, tzinfo=UTC)


def test_winning_outcome_reads_frozen_prices():
    assert closed_market().winning_outcome == "Yes"
    assert closed_market(outcomePrices='["0", "1"]').winning_outcome == "No"


def test_winning_outcome_none_when_open_or_indecisive():
    assert closed_market(closed=False).winning_outcome is None
    # 50/50 prices are not a resolution
    assert closed_market(outcomePrices='["0.5", "0.5"]').winning_outcome is None
    assert closed_market(outcomePrices='["junk", "0"]').winning_outcome is None
    assert closed_market(outcomePrices="[]").winning_outcome is None


# -- status tokens ------------------------------------------------------------


def test_market_status_trading():
    future = datetime.now(UTC) + timedelta(days=3)
    m = closed_market(closed=False, closedTime=None, endDate=future.isoformat())
    assert fmt.market_status(m).startswith("ends ")


def test_market_status_awaiting_resolution():
    past = datetime.now(UTC) - timedelta(days=1)
    m = closed_market(closed=False, closedTime=None, endDate=past.isoformat())
    assert fmt.market_status(m) == "ended - awaiting resolution"


def test_market_status_resolved():
    assert fmt.market_status(closed_market()) == "resolved - Yes won Nov 6 2024"


def test_market_status_closed_without_winner():
    m = closed_market(outcomePrices='["0.5", "0.5"]')
    assert fmt.market_status(m) == "closed Nov 6 2024"


def test_event_status_states():
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert fmt.event_status(Event.model_validate({"endDate": future})).startswith("ends ")
    assert (
        fmt.event_status(Event.model_validate({"endDate": past}))
        == "ended - awaiting resolution"
    )
    assert fmt.event_status(Event.model_validate({"endDate": past, "closed": True})) == "closed"


def test_resolved_event_falls_back_to_closed_markets():
    """A fully-closed event must still drill somewhere: its closed markets
    are the content, winner first under the price sort."""
    event = Event.model_validate(
        {
            "closed": True,
            "sortBy": "price",
            "markets": [
                closed_market(question="loser", outcomePrices='["0", "1"]').model_dump(
                    by_alias=True
                ),
                closed_market(question="winner").model_dump(by_alias=True),
            ],
        }
    )
    assert [m.question for m in event.active_markets] == ["winner", "loser"]
    assert event.top_market is not None and event.top_market.question == "winner"


def test_open_event_still_hides_closed_markets():
    open_m = closed_market(question="open", closed=False, closedTime=None).model_dump(
        by_alias=True
    )
    closed_m = closed_market(question="done").model_dump(by_alias=True)
    event = Event.model_validate({"markets": [open_m, closed_m]})
    assert [m.question for m in event.active_markets] == ["open"]


# -- anchored history fetches ---------------------------------------------------


class RecordingClient(ClobPublicClient):
    """Captures request params; serves a configurable canned history."""

    def __init__(self, history=None):
        super().__init__(client=object())  # never used; _get is overridden
        self.calls: list[dict] = []
        self._canned = history or []

    async def _get(self, path: str, params=None):
        assert path == "/prices-history"
        self.calls.append(dict(params))
        return {"history": list(self._canned)}


async def test_history_without_anchor_uses_interval_params():
    client = RecordingClient()
    await client.prices_history("tok", "1D")
    assert client.calls == [{"market": "tok", "interval": "1d", "fidelity": 60}]


async def test_history_all_ignores_anchor():
    # interval=max spans the lifetime regardless of market state - no ranges.
    client = RecordingClient()
    await client.prices_history("tok", "ALL", end_ts=CLOSE_TS)
    assert client.calls == [{"market": "tok", "interval": "max", "fidelity": 1440}]


async def test_history_anchored_day_is_one_range():
    client = RecordingClient()
    await client.prices_history("tok", "1D", end_ts=CLOSE_TS)
    assert client.calls == [
        {"market": "tok", "startTs": CLOSE_TS - 86_400, "endTs": CLOSE_TS, "fidelity": 60}
    ]


async def test_history_anchored_month_stitches_15d_chunks():
    client = RecordingClient(history=[{"t": 1, "p": 0.5}])
    points = await client.prices_history("tok", "1M", end_ts=CLOSE_TS)
    assert len(client.calls) == 2
    for call in client.calls:
        assert call["endTs"] - call["startTs"] <= MAX_RANGE_SECONDS
    # chunks are contiguous and cover exactly the 30d window
    assert client.calls[0]["startTs"] == CLOSE_TS - 2_592_000
    assert client.calls[0]["endTs"] == client.calls[1]["startTs"]
    assert client.calls[1]["endTs"] == CLOSE_TS
    # the same sample returned in both chunks is deduped
    assert len(points) == 1
