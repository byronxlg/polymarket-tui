"""The cancel-confirm detail block must show every field of the order."""

from __future__ import annotations

from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.ui.widgets.order_details import order_detail_text


def test_order_detail_text_shows_every_field() -> None:
    order = OpenOrder(
        id="0xabcdef1234567890",
        asset_id="111",
        side="BUY",
        price=0.334,
        original_size=100,
        size_matched=40,
        outcome="Yes",
        created_at=1_700_000_000,
    )
    text = order_detail_text(order, title="Will it rain?").plain
    # side / outcome / price
    assert "BUY" in text
    assert "Yes" in text
    assert "33.4" in text  # price in cents
    # full size split so the user sees exactly what remains (resting leads)
    assert "resting 60" in text
    assert "40 filled of 100" in text
    # provenance
    assert "Will it rain?" in text
    assert "placed" in text
    assert "0xabcdef1234" in text  # order id (truncated)


def test_order_detail_text_without_title_or_id() -> None:
    order = OpenOrder(asset_id="222", side="SELL", price=0.5, original_size=5, outcome="No")
    text = order_detail_text(order).plain
    assert "SELL" in text
    assert "No" in text
    assert "resting 5" in text
    assert "placed unknown" in text  # no created_at
