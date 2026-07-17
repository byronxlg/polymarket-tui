"""Table-driven tests for the order validation pipeline."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from polymarket_tui.core.config import BUILDER_CODE, Settings
from polymarket_tui.models.market import Market, OrderBook
from polymarket_tui.services.orders import (
    IssueLevel,
    OrderDraft,
    OrderService,
    PlaceResult,
    Side,
    Tif,
    fill_split,
    fill_split_label,
    format_cents_input,
    format_price_cents,
    format_shares,
    map_error,
    parse_price,
    placement_label,
    price_decimals,
    round_to_tick,
    tick_size,
)


def make_market(**overrides) -> Market:
    base = {
        "question": "Test market?",
        "slug": "test-market",
        "clobTokenIds": '["111", "222"]',
        "outcomes": '["Yes", "No"]',
        "active": True,
        "closed": False,
        "orderPriceMinTickSize": 0.001,
        "orderMinSize": 5,
        "endDate": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
    }
    base.update(overrides)
    return Market.model_validate(base)


def make_book(bid: float = 0.32, ask: float = 0.34, tick: str | None = None) -> OrderBook:
    raw = {
        "bids": [{"price": str(bid), "size": "100"}],
        "asks": [{"price": str(ask), "size": "100"}],
    }
    if tick is not None:
        raw["tick_size"] = tick  # the CLOB stamps this on every book
    return OrderBook.model_validate(raw)


def make_draft(**overrides) -> OrderDraft:
    base = dict(
        market=make_market(),
        token_id="111",
        outcome_label="Yes",
        side=Side.BUY,
        price=Decimal("0.330"),
        size=Decimal("10"),
        tif=Tif.GTC,
        is_market_order=False,
    )
    base.update(overrides)
    return OrderDraft(**base)


@pytest.fixture(autouse=True)
def isolated_audit(tmp_path, monkeypatch):
    """Keep test orders/cancels out of the real ~/.local/share audit log."""
    import polymarket_tui.services.orders as orders_module

    monkeypatch.setattr(orders_module, "AUDIT_PATH", tmp_path / "orders.jsonl")


@pytest.fixture
def service() -> OrderService:
    return OrderService(Settings(pmtui_max_notional=500), authed=None)


def levels(issues) -> set[str]:
    return {i.level.value for i in issues}


def messages(issues) -> str:
    return " | ".join(i.message for i in issues)


class TestValidation:
    def test_clean_order_passes(self, service):
        issues = service.validate(make_draft(), make_book(), cash_balance=100.0, position_size=None)
        assert issues == []

    def test_closed_market_blocks(self, service):
        draft = make_draft(market=make_market(closed=True))
        issues = service.validate(draft, make_book(), 100.0, None)
        assert IssueLevel.BLOCK in {i.level for i in issues}
        assert "closed" in messages(issues).lower()

    def test_not_accepting_orders_blocks(self, service):
        draft = make_draft(market=make_market(acceptingOrders=False))
        issues = service.validate(draft, make_book(), 100.0, None)
        assert IssueLevel.BLOCK in {i.level for i in issues}
        assert "not accepting orders" in messages(issues).lower()

    def test_past_end_date_still_accepting_passes(self, service):
        # Markets awaiting resolution (e.g. yesterday's weather) trade past
        # endDate; the exchange accepts, so we must not block.
        past = (datetime.now(UTC) - timedelta(hours=20)).isoformat()
        draft = make_draft(market=make_market(endDate=past, acceptingOrders=True))
        issues = service.validate(draft, make_book(), 100.0, None)
        assert issues == []

    def test_price_out_of_bounds_blocks(self, service):
        for bad in (Decimal("0"), Decimal("1"), Decimal("1.5"), Decimal("-0.1")):
            issues = service.validate(make_draft(price=bad), make_book(), 100.0, None)
            assert "between" in messages(issues)

    def test_off_tick_price_blocks_with_suggestion(self, service):
        draft = make_draft(price=Decimal("0.3305"))
        issues = service.validate(draft, make_book(), 100.0, None)
        assert "multiple" in messages(issues)
        assert "33.1c" in messages(issues) or "33.0c" in messages(issues)

    def test_below_min_size_blocks(self, service):
        issues = service.validate(make_draft(size=Decimal("2")), make_book(), 100.0, None)
        assert "Minimum" in messages(issues)

    def test_insufficient_cash_blocks_buy(self, service):
        issues = service.validate(make_draft(size=Decimal("100")), make_book(), 10.0, None)
        assert "cash" in messages(issues).lower()

    def test_sell_more_than_held_blocks(self, service):
        draft = make_draft(side=Side.SELL, size=Decimal("50"))
        issues = service.validate(draft, make_book(), 100.0, position_size=10.0)
        assert "hold" in messages(issues)

    def test_sell_within_position_passes(self, service):
        draft = make_draft(side=Side.SELL, size=Decimal("10"), price=Decimal("0.330"))
        issues = service.validate(draft, make_book(), None, position_size=50.0)
        assert [i for i in issues if i.level is IssueLevel.BLOCK] == []

    def test_sell_with_unknown_position_does_not_block(self, service):
        # position_size=None means holdings failed to load; must not hard-block a
        # sell the exchange would accept (issue #8, mirrors the BUY cash guard).
        draft = make_draft(side=Side.SELL, size=Decimal("50"), price=Decimal("0.330"))
        issues = service.validate(draft, make_book(), 100.0, position_size=None)
        assert [i for i in issues if i.level is IssueLevel.BLOCK] == []
        assert "hold" not in messages(issues)

    def test_price_far_from_mid_warns_never_blocks(self, service):
        # mid = 33c; 40c is >10% off -> advisory only, the user decides
        issues = service.validate(make_draft(price=Decimal("0.40")), make_book(), 100.0, None)
        assert "off mid" in messages(issues)
        assert all(i.level is IssueLevel.WARN for i in issues)

    def test_price_slightly_off_mid_is_silent(self, service):
        # mid = 33c; 32c is ~3% off -> no nagging
        issues = service.validate(make_draft(price=Decimal("0.320")), make_book(), 100.0, None)
        assert issues == []

    def test_crossing_the_spread_is_silent(self, service):
        issues = service.validate(make_draft(price=Decimal("0.340")), make_book(), 100.0, None)
        assert issues == []

    def test_market_order_skips_mid_check(self, service):
        draft = make_draft(is_market_order=True, price=Decimal("0.340"), tif=Tif.FAK)
        issues = service.validate(draft, make_book(), 100.0, None)
        assert not any("off mid" in i.message for i in issues)

    def test_max_notional_warns_never_blocks(self, service):
        draft = make_draft(price=Decimal("0.90"), size=Decimal("600"))
        issues = service.validate(draft, make_book(bid=0.89, ask=0.91), 10_000.0, None)
        assert "PMTUI_MAX_NOTIONAL" in messages(issues)
        assert all(i.level is IssueLevel.WARN for i in issues)

    def test_duplicate_guard_warns_never_blocks(self, service):
        draft = make_draft()
        service._recent.append(
            (
                __import__("time").monotonic(),
                f"{draft.token_id}|{draft.side}|{draft.price}|{draft.size}",
            )
        )
        issues = service.validate(draft, make_book(), 100.0, None)
        assert "Identical" in messages(issues)
        assert all(i.level is IssueLevel.WARN for i in issues)

    def test_only_exchange_reject_mirrors_block(self, service):
        """Policy: hard blocks exist only for orders the exchange would reject."""
        draft = make_draft(price=Decimal("0.90"), size=Decimal("600"))
        issues = service.validate(draft, make_book(bid=0.89, ask=0.91), 10_000.0, None)
        assert IssueLevel.BLOCK not in {i.level for i in issues}

    def test_no_book_no_balance_still_validates_structure(self, service):
        issues = service.validate(make_draft(), None, None, None)
        assert issues == []


class FakeAuthed:
    """Records cancel calls and returns a canned CLOB cancel response."""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[str] = []

    async def cancel_order(self, order_id: str) -> dict:
        self.calls.append(order_id)
        return self.response


class TestCancel:
    @pytest.mark.asyncio
    async def test_dry_mode_never_posts_cancel(self):
        authed = FakeAuthed({"canceled": ["0xabc"], "not_canceled": {}})
        service = OrderService(Settings(polymarket_execution_live=False), authed)
        result = await service.cancel("0xabc")
        assert result.ok and result.dry_run
        assert authed.calls == []  # the exchange was never touched

    @pytest.mark.asyncio
    async def test_live_cancel_success(self):
        authed = FakeAuthed({"canceled": ["0xabc"], "not_canceled": {}})
        service = OrderService(
            Settings(
                polymarket_execution_live=True,
                polymarket_private_key="k",
                polymarket_funder="0xf",
            ),
            authed,
        )
        result = await service.cancel("0xabc")
        assert result.ok and not result.dry_run
        assert authed.calls == ["0xabc"]

    @pytest.mark.asyncio
    async def test_live_cancel_declined_in_200_response(self):
        authed = FakeAuthed({"canceled": [], "not_canceled": {"0xabc": "order already matched"}})
        service = OrderService(
            Settings(
                polymarket_execution_live=True,
                polymarket_private_key="k",
                polymarket_funder="0xf",
            ),
            authed,
        )
        result = await service.cancel("0xabc")
        assert not result.ok
        assert "matched" in result.error

    @pytest.mark.asyncio
    async def test_unauthenticated_cancel_fails_cleanly(self):
        service = OrderService(Settings(), authed=None)
        result = await service.cancel("0xabc")
        assert not result.ok


class FakeSigner:
    """Signs (dry-run) without posting; records whether posting was attempted."""

    def __init__(self) -> None:
        self.posted = False

    async def sign_order(self, order_args) -> object:
        return object()

    async def create_and_post_order(self, order_args, order_type) -> dict:
        self.posted = True
        return {"success": True, "status": "matched", "orderID": "0x1"}


class TimeoutPoster:
    """Signs fine; posting raises (a network timeout after the request left)."""

    async def sign_order(self, order_args) -> object:
        return object()

    async def create_and_post_order(self, order_args, order_type) -> dict:
        raise TimeoutError("read timed out")


class TickAwareAuthed:
    """A signer that also reports the tick the CLOB client would sign at, so the
    place() tick reconciliation can be exercised without a real client."""

    def __init__(self, client_tick: str | None) -> None:
        self._client_tick = client_tick
        self.signed = False
        self.posted = False

    async def resolved_tick(self, token_id: str, *, refresh: bool = True) -> Decimal | None:
        return Decimal(self._client_tick) if self._client_tick is not None else None

    async def sign_order(self, order_args) -> object:
        self.signed = True
        return object()

    async def create_and_post_order(self, order_args, order_type) -> dict:
        self.posted = True
        return {"success": True, "status": "matched", "orderID": "0x1"}


def _live_settings() -> Settings:
    return Settings(
        polymarket_execution_live=True,
        polymarket_funder="0xf",
        polymarket_private_key="deadbeef" * 8,
    )


class TestTickReconciliation:
    """The bug: the user sets 98.1c but a 98.0c order is placed. The CLOB client
    caches a token's tick for the whole session and its price_valid only bounds-
    checks, so a stale coarse 0.01 tick silently rounds 0.981 -> 0.98 at signing.
    place() must refuse to sign a price the client would alter, and never post."""

    @pytest.mark.asyncio
    async def test_live_order_refused_when_client_would_round_to_coarser_tick(self):
        authed = TickAwareAuthed(client_tick="0.01")  # stale-coarse vs the book's 0.001
        service = OrderService(_live_settings(), authed)
        draft = make_draft(price=Decimal("0.981"), tick=Decimal("0.001"))
        result = await service.place(draft)
        assert not result.ok and not result.dry_run
        assert not result.status_unknown  # nothing was sent - not a timeout
        assert authed.posted is False and authed.signed is False
        assert "98.1c" in result.error and "rounded" in result.error.lower()
        # Refused before the duplicate fingerprint is seeded (nothing was placed).
        assert service._recent == []

    @pytest.mark.asyncio
    async def test_live_order_posts_when_client_tick_matches_the_book(self):
        authed = TickAwareAuthed(client_tick="0.001")
        service = OrderService(_live_settings(), authed)
        draft = make_draft(price=Decimal("0.981"), tick=Decimal("0.001"))
        result = await service.place(draft)
        assert result.ok and not result.dry_run
        assert authed.posted is True

    @pytest.mark.asyncio
    async def test_client_tick_finer_than_the_book_still_posts(self):
        # A finer client tick (0.0001) can represent 0.981 exactly - not a block.
        authed = TickAwareAuthed(client_tick="0.0001")
        service = OrderService(_live_settings(), authed)
        draft = make_draft(price=Decimal("0.981"), tick=Decimal("0.001"))
        result = await service.place(draft)
        assert result.ok and authed.posted is True

    @pytest.mark.asyncio
    async def test_unreadable_client_tick_does_not_block(self):
        # If the tick cannot be read, proceed as before (no regression) - the
        # cache was still dropped, so the next resolve is fresh.
        authed = TickAwareAuthed(client_tick=None)
        service = OrderService(_live_settings(), authed)
        draft = make_draft(price=Decimal("0.981"), tick=Decimal("0.001"))
        result = await service.place(draft)
        assert result.ok and authed.posted is True

    @pytest.mark.asyncio
    async def test_dry_run_also_refuses_a_coarsening_tick(self):
        authed = TickAwareAuthed(client_tick="0.01")
        service = OrderService(
            Settings(polymarket_private_key="k", polymarket_funder="0xf"), authed
        )
        draft = make_draft(price=Decimal("0.981"), tick=Decimal("0.001"))
        result = await service.place(draft)
        assert not result.ok and result.dry_run
        assert authed.signed is False


class FakeClobForTick:
    """Stands in for py-clob-client-v2's ClobClient: a per-session tick cache
    under the same name-mangled attribute, and a get_tick_size that re-reads a
    'server' value only on a cache miss."""

    def __init__(self, server_tick: str, cached: str | None = None) -> None:
        self.server_tick = server_tick
        setattr(
            self,
            f"_{type(self).__name__}__tick_sizes",
            {} if cached is None else {"111": cached},
        )
        self.fetches = 0

    def get_tick_size(self, token_id: str) -> str:
        cache = getattr(self, f"_{type(self).__name__}__tick_sizes")
        if token_id in cache:
            return cache[token_id]
        self.fetches += 1
        cache[token_id] = self.server_tick
        return self.server_tick


class TestResolvedTick:
    def _authed(self, client):
        from polymarket_tui.api.clob_auth import AuthedClobClient

        authed = AuthedClobClient(Settings())
        authed._client = client  # skip the real bootstrap
        return authed

    @pytest.mark.asyncio
    async def test_refresh_drops_a_stale_cache_and_rereads_the_exchange(self):
        client = FakeClobForTick(server_tick="0.001", cached="0.01")  # session re-gridded
        tick = await self._authed(client).resolved_tick("111", refresh=True)
        assert tick == Decimal("0.001")  # fresh value, not the stale 0.01
        assert client.fetches == 1

    @pytest.mark.asyncio
    async def test_without_refresh_the_cached_value_is_used(self):
        client = FakeClobForTick(server_tick="0.001", cached="0.01")
        tick = await self._authed(client).resolved_tick("111", refresh=False)
        assert tick == Decimal("0.01") and client.fetches == 0

    @pytest.mark.asyncio
    async def test_returns_none_when_the_tick_cannot_be_read(self):
        class Boom:
            def get_tick_size(self, token_id):
                raise RuntimeError("clob unreachable")

        assert await self._authed(Boom()).resolved_tick("111") is None


class TestPlace:
    @pytest.mark.asyncio
    async def test_live_post_timeout_is_status_unknown_and_audited(self):
        """The dangerous path: a timed-out post may have landed. It must be
        flagged status-unknown (drives the factual status-unknown modal), keep
        the seeded duplicate fingerprint, and land in the audit log - never
        retried."""
        import json as json_module

        import polymarket_tui.services.orders as orders_module

        live = Settings(
            polymarket_execution_live=True,
            polymarket_funder="0xf",
            polymarket_private_key="deadbeef" * 8,
        )
        service = OrderService(live, TimeoutPoster())
        result = await service.place(make_draft())
        assert not result.ok and not result.dry_run
        assert result.status_unknown
        # Seeded BEFORE the post: it may have landed, so an identical order
        # within the window must warn.
        assert len(service._recent) == 1
        entry = json_module.loads(
            orders_module.AUDIT_PATH.read_text().strip().splitlines()[-1]
        )
        assert entry["ok"] is False
        assert "status unknown" in entry["error"].lower()

    def test_place_result_status_unknown_flag(self):
        unknown = PlaceResult(
            ok=False, dry_run=False, error="Order status unknown (timeout) - check Open Orders."
        )
        assert unknown.status_unknown is True
        # A dry run or a plain rejection is not status-unknown.
        assert PlaceResult(ok=True, dry_run=True, status="signed").status_unknown is False
        assert PlaceResult(ok=False, dry_run=False, error="closed market").status_unknown is False

    @pytest.mark.asyncio
    async def test_dry_run_does_not_post_or_seed_duplicate_guard(self):
        # A dry run signs but places nothing, so it must not seed the duplicate
        # fingerprint (issue #8) - a later genuine attempt shouldn't warn.
        authed = FakeSigner()
        service = OrderService(Settings(polymarket_execution_live=False), authed)
        result = await service.place(make_draft())
        assert result.ok and result.dry_run
        assert authed.posted is False
        assert service._recent == []

    @pytest.mark.asyncio
    async def test_live_post_seeds_duplicate_guard(self):
        authed = FakeSigner()
        live = Settings(
            polymarket_execution_live=True,
            polymarket_funder="0xf",
            polymarket_private_key="deadbeef" * 8,
        )
        service = OrderService(live, authed)
        result = await service.place(make_draft())
        assert result.ok and not result.dry_run
        assert authed.posted is True
        assert len(service._recent) == 1


class TestLiveTick:
    """The exchange re-grids a market (0.01 -> 0.001) as its price nears 0 or 1.
    Gamma's orderPriceMinTickSize is a snapshot taken when the pane opened, so
    the book's own tick_size wins wherever a book is in hand."""

    def test_book_tick_overrides_a_stale_gamma_snapshot(self):
        market = make_market(orderPriceMinTickSize=0.01)  # stale: exchange moved to 0.001
        book = make_book(tick="0.001")
        assert tick_size(market, book) == Decimal("0.001")
        assert price_decimals(market, book) == 1
        assert round_to_tick(market, Decimal("0.334"), book) == Decimal("0.334")

    def test_stale_tick_no_longer_blocks_a_price_the_exchange_accepts(self):
        # The reported bug: a legal 33.4c order rejected as "not a multiple of 0.01".
        market = make_market(orderPriceMinTickSize=0.01)
        draft = make_draft(market=market, price=Decimal("0.334"))
        service = OrderService(Settings(pmtui_max_notional=500), authed=None)
        issues = service.validate(draft, make_book(tick="0.001"), 100.0, None)
        assert not [i for i in issues if i.level is IssueLevel.BLOCK]

    def test_off_tick_still_blocks_against_the_live_tick(self):
        # The block must still fire - just against the exchange's real grid.
        market = make_market(orderPriceMinTickSize=0.001)
        draft = make_draft(market=market, price=Decimal("0.3345"))
        service = OrderService(Settings(pmtui_max_notional=500), authed=None)
        issues = service.validate(draft, make_book(tick="0.001"), 100.0, None)
        blocks = [i for i in issues if i.level is IssueLevel.BLOCK]
        assert len(blocks) == 1 and "multiple of 0.001" in blocks[0].message

    def test_falls_back_to_gamma_before_the_first_book_arrives(self):
        market = make_market(orderPriceMinTickSize=0.001)
        assert tick_size(market, None) == Decimal("0.001")
        # A book from before this field existed carries no tick: fall back, never crash.
        assert tick_size(market, make_book()) == Decimal("0.001")

    def test_missing_tick_everywhere_falls_back_to_the_coarser_penny(self):
        # Coarse is the safe direction: visibly wrong, rather than silently
        # offering sub-tick prices the exchange would reject.
        assert tick_size(make_market(orderPriceMinTickSize=None), None) == Decimal("0.01")

    def test_non_power_of_ten_tick(self):
        # World Cup markets trade on 0.0025 -> 0.25c -> 2 decimal places.
        market = make_market(orderPriceMinTickSize=0.01)
        book = make_book(tick="0.0025")
        assert price_decimals(market, book) == 2
        assert round_to_tick(market, Decimal("0.3340"), book) == Decimal("0.3350")

    def test_draft_price_label_uses_the_tick_it_was_drafted_at(self):
        draft = make_draft(
            market=make_market(orderPriceMinTickSize=0.01),
            price=Decimal("0.334"),
            tick=Decimal("0.001"),
        )
        assert draft.price_label() == "33.4c"
        assert "33.4c" in draft.summary()


class TestHelpers:
    def test_round_to_tick(self):
        market = make_market(orderPriceMinTickSize=0.01)
        assert round_to_tick(market, Decimal("0.333")) == Decimal("0.33")
        assert round_to_tick(market, Decimal("0.335")) == Decimal("0.34")

    def test_map_error(self):
        assert "USDC" in map_error("not enough balance / allowance")
        assert "tick" in map_error("invalid tick size for market")
        assert "minimum" in map_error("size below minimum size").lower()
        assert map_error("weird thing") == "weird thing"
        assert "rejected" in map_error("")

    def test_parse_price_is_cents(self):
        # Bare numbers are always cents - no unit guessing.
        assert parse_price("12.3") == Decimal("0.123")
        assert parse_price("12.3c") == Decimal("0.123")
        assert parse_price("1") == Decimal("0.01")
        assert parse_price("0.1") == Decimal("0.001")
        assert parse_price("99.9") == Decimal("0.999")
        assert parse_price("$0.5") is None  # no dollars entry - cents only
        assert parse_price("") is None
        assert parse_price("abc") is None


class CapturingAuthed:
    """Captures the OrderArgs handed to the signing path (dry-run)."""

    def __init__(self) -> None:
        self.order_args = None

    async def sign_order(self, order_args) -> object:
        self.order_args = order_args
        return object()


def dry_service(authed) -> OrderService:
    # Key + funder => TRADER_DRY (execution_live defaults False).
    return OrderService(
        Settings(polymarket_private_key="k", polymarket_funder="0xf"),
        authed,
    )


class TestBuilderCode:
    def test_shipped_code_is_valid_bytes32(self):
        # Guard against a typo in the constant: must be 0x + 64 hex, non-zero.
        assert re.fullmatch(r"0x[0-9a-f]{64}", BUILDER_CODE)
        assert int(BUILDER_CODE, 16) != 0

    @pytest.mark.asyncio
    async def test_place_always_stamps_the_hardcoded_code(self):
        # Every order - including other users' - is attributed to the shipped
        # code. It is not configurable, so this is the only value that can appear.
        authed = CapturingAuthed()
        result = await dry_service(authed).place(make_draft())
        assert result.ok and result.dry_run
        assert authed.order_args.builder_code == BUILDER_CODE

    def test_builder_code_is_not_a_settings_field(self):
        # No env/config override exists to redirect attribution away from us.
        assert "polymarket_builder_code" not in Settings.model_fields


class TestConfirmFormatting:
    """What the confirm card shows must be exactly what is signed."""

    def test_price_keeps_tick_resolution(self):
        # 33.45c on a 0.01c-tick market must not display rounded to 33.4c.
        market = make_market(orderPriceMinTickSize=0.0001)
        assert format_price_cents(market, Decimal("0.3345")) == "33.45c"

    def test_price_min_one_decimal(self):
        # Coarser ticks keep the app-wide one-decimal cents convention.
        assert format_price_cents(make_market(orderPriceMinTickSize=0.01), Decimal("0.33")) == (
            "33.0c"
        )
        assert format_price_cents(make_market(orderPriceMinTickSize=0.001), Decimal("0.333")) == (
            "33.3c"
        )

    def test_shares_keep_fractions(self):
        # A 50% sell of a 25.5-share position is 12.75 shares - not "13".
        assert format_shares(Decimal("12.75")) == "12.75"
        assert format_shares(Decimal("12.5")) == "12.5"
        assert format_shares(Decimal("10")) == "10"
        assert format_shares(Decimal("1234")) == "1,234"

    def test_summary_round_trips_fine_prices_and_sizes(self):
        draft = make_draft(
            market=make_market(orderPriceMinTickSize=0.0001),
            price=Decimal("0.3345"),
            size=Decimal("12.5"),
        )
        assert "33.45c" in draft.summary()
        assert "12.5" in draft.summary()

    def test_zero_size_reports_single_block(self):
        service = OrderService(Settings(pmtui_max_notional=500), authed=None)
        issues = service.validate(make_draft(size=Decimal("0")), make_book(), 100.0, None)
        blocks = [i for i in issues if i.level is IssueLevel.BLOCK]
        assert len(blocks) == 1
        assert "positive" in blocks[0].message

    def test_tick_suggestion_keeps_resolution(self):
        market = make_market(orderPriceMinTickSize=0.0001)
        draft = make_draft(market=market, price=Decimal("0.33455"))
        service = OrderService(Settings(pmtui_max_notional=500), authed=None)
        issues = service.validate(draft, make_book(), 100.0, None)
        # nearest valid is 33.46c (round half up) - shown at full resolution
        assert "33.46c" in messages(issues)


class TestPriceDecimals:
    def test_common_ticks(self):
        assert price_decimals(make_market(orderPriceMinTickSize=0.01)) == 0
        assert price_decimals(make_market(orderPriceMinTickSize=0.001)) == 1
        assert price_decimals(make_market(orderPriceMinTickSize=0.0001)) == 2

    def test_missing_tick_defaults_to_one_cent(self):
        # _tick falls back to 0.01 (1c) -> whole-cent prices, 0 decimals.
        assert price_decimals(make_market(orderPriceMinTickSize=0)) == 0


class TestFormatCentsInput:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", ""),
            ("3", "3"),
            ("33", "33"),
            ("334", "33.4"),  # decimal auto-inserted before the 3rd digit
            ("999", "99.9"),
            ("3345", "33.4"),  # 4th digit past 0.1c resolution is dropped
            ("100", "10.0"),  # 100c is not placeable; two whole-cent digits max
            ("5.5", "5.5"),  # an explicit dot is honoured
            ("33.", "33."),  # trailing dot kept so a fraction can follow
            ("05", "5"),  # leading zero stripped
        ],
    )
    def test_one_decimal_resolution(self, raw, expected):
        assert format_cents_input(raw, 1) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("334", "33"),  # no fractional cents at a 1c tick
            ("33.4", "33"),  # a typed dot cannot add precision the tick lacks
            ("99", "99"),
            (".", ""),
        ],
    )
    def test_whole_cent_resolution(self, raw, expected):
        assert format_cents_input(raw, 0) == expected

    def test_two_decimal_resolution(self):
        assert format_cents_input("3345", 2) == "33.45"
        assert format_cents_input("33456", 2) == "33.45"

    def test_result_always_reparses_to_the_shown_value(self):
        # Whatever the field shows must parse back (no display-only artifacts).
        for raw in ("334", "999", "5.5", "33."):
            shown = format_cents_input(raw, 1)
            if shown and shown != "33.":
                assert parse_price(shown) is not None


# -- fill split: does this order fill now, or rest on the book? -----------------


def deep_book(bids: list[tuple[str, str]], asks: list[tuple[str, str]]) -> OrderBook:
    return OrderBook.model_validate(
        {
            "bids": [{"price": p, "size": s} for p, s in bids],
            "asks": [{"price": p, "size": s} for p, s in asks],
        }
    )


def test_fill_split_none_without_a_book():
    assert fill_split(make_draft(), None) is None


def test_sell_at_the_bid_rests_the_part_the_bid_cannot_absorb():
    """The cash-out prefill: full position at the best bid, GTC. The bid holds
    40 of the 100 shares, so 60 rest on the book - silently, before this."""
    book = deep_book(bids=[("0.33", "40"), ("0.32", "500")], asks=[("0.34", "100")])
    draft = make_draft(side=Side.SELL, price=Decimal("0.33"), size=Decimal("100"))
    split = fill_split(draft, book)
    assert (split.fills, split.rests) == (Decimal("40"), Decimal("60"))
    assert not split.fills_all and not split.fills_none
    assert fill_split_label(draft, split) == "fills ~40 now, ~60 rests on the book"


def test_sell_sweeps_every_bid_at_or_above_the_limit():
    book = deep_book(bids=[("0.33", "40"), ("0.32", "500")], asks=[("0.34", "100")])
    draft = make_draft(side=Side.SELL, price=Decimal("0.32"), size=Decimal("100"))
    split = fill_split(draft, book)
    assert split.fills == Decimal("100") and split.fills_all
    assert fill_split_label(draft, split) == "fills all ~100 now"


def test_sell_above_the_bid_rests_entirely():
    book = deep_book(bids=[("0.33", "1000")], asks=[("0.36", "100")])
    draft = make_draft(side=Side.SELL, price=Decimal("0.35"), size=Decimal("10"))
    split = fill_split(draft, book)
    assert split.fills_none and split.rests == Decimal("10")
    assert fill_split_label(draft, split) == "nothing fills now - it rests on the book"


def test_buy_crosses_only_asks_at_or_below_the_limit():
    book = deep_book(bids=[("0.30", "999")], asks=[("0.34", "25"), ("0.35", "999")])
    draft = make_draft(side=Side.BUY, price=Decimal("0.34"), size=Decimal("60"))
    split = fill_split(draft, book)
    assert (split.fills, split.rests) == (Decimal("25"), Decimal("35"))


def test_market_order_remainder_is_cancelled_not_rested():
    """A market order is a FAK marketable limit at the touch: what the touch
    cannot absorb is killed, and must never read as 'rests on the book'."""
    book = deep_book(bids=[("0.33", "40"), ("0.32", "500")], asks=[("0.34", "100")])
    draft = make_draft(
        side=Side.SELL,
        price=Decimal("0.33"),
        size=Decimal("100"),
        tif=Tif.FAK,
        is_market_order=True,
    )
    split = fill_split(draft, book)
    assert (split.fills, split.rests) == (Decimal("40"), Decimal("60"))
    assert fill_split_label(draft, split) == "fills ~40 now, ~60 cancelled"


def test_fok_fills_all_or_nothing():
    book = deep_book(bids=[("0.33", "40")], asks=[("0.34", "100")])
    draft = make_draft(side=Side.SELL, price=Decimal("0.33"), size=Decimal("100"), tif=Tif.FOK)
    split = fill_split(draft, book)
    assert split.fills_none and split.fills == Decimal("0")
    assert "killed" in fill_split_label(draft, split)
    # ...but a book deep enough fills the whole thing.
    deep = deep_book(bids=[("0.33", "100")], asks=[("0.34", "100")])
    assert fill_split(draft, deep).fills_all


def test_fok_that_fills_exactly_is_not_killed():
    book = deep_book(bids=[("0.33", "100")], asks=[("0.34", "1")])
    draft = make_draft(side=Side.SELL, price=Decimal("0.33"), size=Decimal("100"), tif=Tif.FOK)
    assert fill_split(draft, book).fills_all


def test_empty_book_side_fills_nothing():
    draft = make_draft(side=Side.SELL, price=Decimal("0.33"), size=Decimal("10"))
    assert fill_split(draft, deep_book(bids=[], asks=[("0.34", "5")])).fills_none


# -- placement_label: assert only what the CLOB status proves ------------------


def test_placement_label_live_says_nothing_filled():
    draft = make_draft(side=Side.SELL, size=Decimal("100"), price=Decimal("0.334"))
    label = placement_label(draft, PlaceResult(ok=True, dry_run=False, status="live"))
    assert label == "Resting on the book: SELL 100 YES @ 33.4c - nothing filled"


def test_placement_label_matched_gtc_never_claims_a_fill_size():
    """`matched` proves the order crossed, not that it crossed fully - a GTC
    remainder rests. The response has no trustworthy fill size, so don't invent
    one; point at open orders instead."""
    draft = make_draft(side=Side.SELL, size=Decimal("100"), price=Decimal("0.334"))
    label = placement_label(draft, PlaceResult(ok=True, dry_run=False, status="matched"))
    assert label.startswith("Matched: SELL 100 YES @ 33.4c")
    assert "check open orders for any remainder" in label
    assert "Filled" not in label


def test_placement_label_matched_market_order_says_remainder_cancelled():
    draft = make_draft(
        side=Side.SELL,
        size=Decimal("100"),
        price=Decimal("0.334"),
        tif=Tif.FAK,
        is_market_order=True,
    )
    label = placement_label(draft, PlaceResult(ok=True, dry_run=False, status="matched"))
    assert "any remainder was cancelled" in label


def test_placement_label_falls_back_to_the_raw_status():
    draft = make_draft(side=Side.BUY, size=Decimal("5"), price=Decimal("0.5"))
    assert placement_label(draft, PlaceResult(ok=True, dry_run=False, status="delayed")).startswith(
        "Order delayed: BUY 5 YES @ 50.0c"
    )


# -- a full-position prefill must not exceed the position ----------------------


class TestFullPositionSellDoesNotBlockItself:
    """`s` on a fractional holding prefills the whole position. Rounding that
    prefill to 2dp rounded it UP past the holding, so the app's own inventory
    guard hard-blocked it - with both numbers rendered as whole shares, the
    message read "Selling 28 but you hold 28."  (Real position: 28.3393.)"""

    HELD = 28.3393

    def test_format_shares_keeps_every_fraction_digit(self):
        assert format_shares(Decimal("28.3393")) == "28.3393"
        assert format_shares(Decimal("1234.5")) == "1,234.5"
        assert format_shares(Decimal("10")) == "10"
        assert format_shares(Decimal("0")) == "0"

    def test_prefilling_the_whole_position_validates_clean(self, service):
        draft = make_draft(side=Side.SELL, size=Decimal(str(self.HELD)), price=Decimal("0.33"))
        issues = service.validate(draft, make_book(), cash_balance=1000.0, position_size=self.HELD)
        assert IssueLevel.BLOCK.value not in levels(issues), messages(issues)

    def test_a_size_above_the_holding_still_blocks_and_names_both_numbers(self, service):
        draft = make_draft(side=Side.SELL, size=Decimal("28.34"), price=Decimal("0.33"))
        issues = service.validate(draft, make_book(), cash_balance=1000.0, position_size=self.HELD)
        assert IssueLevel.BLOCK.value in levels(issues)
        assert "Selling 28.34 but you hold 28.3393." in messages(issues)
