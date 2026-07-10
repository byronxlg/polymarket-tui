"""The order form follows the exchange's tick, not Gamma's snapshot.

MarketPane owns the live book; OrderPanel reaches it through the
`is_market_pane` marker. When the exchange re-grids a market (0.01 -> 0.001 as
its price nears 0 or 1) the form must bump and format at the new tick, or it
snaps a legal 33.4c order back to 33c.
"""

from __future__ import annotations

from decimal import Decimal

from textual.app import App, ComposeResult
from textual.containers import Vertical

from polymarket_tui.core.config import Settings
from polymarket_tui.models.market import Market, OrderBook
from polymarket_tui.services.orders import Side
from polymarket_tui.ui.widgets.order_panel import OrderPanel


def _market(tick: float | None) -> Market:
    return Market.model_validate(
        {
            "question": "Test market?",
            "slug": "test-market",
            "clobTokenIds": '["111", "222"]',
            "outcomes": '["Yes", "No"]',
            "orderPriceMinTickSize": tick,
            "orderMinSize": 5,
        }
    )


def _book(tick: str | None) -> OrderBook:
    raw = {
        "bids": [{"price": "0.333", "size": "100"}],
        "asks": [{"price": "0.335", "size": "100"}],
    }
    if tick is not None:
        raw["tick_size"] = tick
    return OrderBook.model_validate(raw)


class _FakePane(Vertical):
    """Stands in for MarketPane: carries the marker and the live book."""

    is_market_pane = True

    def __init__(self, book: OrderBook) -> None:
        super().__init__()
        self._book = book

    def compose(self) -> ComposeResult:
        yield OrderPanel(id="order-panel")


class _Host(App):
    def __init__(self, book: OrderBook) -> None:
        super().__init__()
        self._book = book
        # The panel reads app.settings to colour the armed confirm (DRY vs LIVE).
        self.settings = Settings(pmtui_max_notional=500)

    def compose(self) -> ComposeResult:
        yield _FakePane(self._book)


async def test_prefill_and_bump_use_the_live_book_tick() -> None:
    # Gamma says 0.01 (stale); the exchange has re-gridded to 0.001.
    market, book = _market(0.01), _book("0.001")
    app = _Host(book)
    async with app.run_test(size=(80, 30)) as pilot:
        panel = app.query_one(OrderPanel)
        panel.open(market, Side.BUY, 0, book)
        await pilot.pause()

        price = panel.query_one("#op-price")
        assert price.value == "33.4", f"mid prefill should keep 0.1c resolution, got {price.value}"

        panel.bump_price(1)
        assert price.value == "33.5", f"one tick up is 0.1c, got {price.value}"
        panel.bump_price(-1)
        assert price.value == "33.4"

        draft, err = panel._current_draft()
        assert not err and draft.tick == Decimal("0.001")
        assert draft.price_label() == "33.4c"


async def test_falls_back_to_gamma_when_the_book_has_no_tick() -> None:
    market, book = _market(0.01), _book(None)
    app = _Host(book)
    async with app.run_test(size=(80, 30)) as pilot:
        panel = app.query_one(OrderPanel)
        panel.open(market, Side.BUY, 0, book)
        await pilot.pause()
        price = panel.query_one("#op-price")
        assert price.value == "33", f"penny tick renders whole cents, got {price.value}"
        panel.bump_price(1)
        assert price.value == "34"
