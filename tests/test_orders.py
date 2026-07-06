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
    Side,
    Tif,
    map_error,
    parse_price,
    round_to_tick,
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


def make_book(bid: float = 0.32, ask: float = 0.34) -> OrderBook:
    return OrderBook.model_validate(
        {"bids": [{"price": str(bid), "size": "100"}], "asks": [{"price": str(ask), "size": "100"}]}
    )


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


class TestPlace:
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
