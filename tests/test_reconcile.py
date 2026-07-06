"""Status-unknown reconciliation matching (issue #3)."""

from __future__ import annotations

from decimal import Decimal

from test_orders import make_draft

from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.services.orders import PlaceResult, ReconcileTarget


def test_place_result_status_unknown_flag():
    unknown = PlaceResult(
        ok=False, dry_run=False, error="Order status unknown (timeout) - check Open Orders."
    )
    assert unknown.status_unknown is True
    # A dry run or a plain rejection is not status-unknown.
    assert PlaceResult(ok=True, dry_run=True, status="signed").status_unknown is False
    assert PlaceResult(ok=False, dry_run=False, error="closed market").status_unknown is False


def test_reconcile_target_from_draft():
    draft = make_draft(token_id="111", side=make_draft().side, price=Decimal("0.330"))
    target = ReconcileTarget.from_draft(draft)
    assert target.token_id == "111"
    assert target.side == "BUY"
    assert target.price == Decimal("0.330")
    assert target.condition_id == draft.market.condition_id


def test_reconcile_matches_resting_order():
    target = ReconcileTarget.from_draft(make_draft(token_id="111", price=Decimal("0.330")))
    resting = OpenOrder(asset_id="111", side="BUY", price=0.33, original_size=10)
    assert target.matches(resting) is True


def test_reconcile_ignores_size_for_partial_fills():
    target = ReconcileTarget.from_draft(make_draft(token_id="111", price=Decimal("0.330")))
    partial = OpenOrder(asset_id="111", side="BUY", price=0.33, original_size=10, size_matched=6)
    assert target.matches(partial) is True


def test_reconcile_matches_lowercase_side():
    # The CLOB's side casing is not ours to assume on the reconcile path.
    target = ReconcileTarget.from_draft(make_draft(token_id="111", price=Decimal("0.330")))
    assert target.matches(OpenOrder(asset_id="111", side="buy", price=0.33)) is True


def test_reconcile_no_match_on_different_token_side_or_price():
    target = ReconcileTarget.from_draft(make_draft(token_id="111", price=Decimal("0.330")))
    assert target.matches(OpenOrder(asset_id="222", side="BUY", price=0.33)) is False
    assert target.matches(OpenOrder(asset_id="111", side="SELL", price=0.33)) is False
    assert target.matches(OpenOrder(asset_id="111", side="BUY", price=0.34)) is False
