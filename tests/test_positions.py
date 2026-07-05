"""Position.resolved_loss: the portfolio screen hides these rows."""

from polymarket_tui.models.portfolio import Position


def test_resolved_loss_is_redeemable_at_zero():
    # Real data-api shape for a losing side after resolution.
    pos = Position(redeemable=True, curPrice=0.0, size=106, currentValue=0.0)
    assert pos.resolved_loss


def test_won_position_is_not_a_loss():
    pos = Position(redeemable=True, curPrice=1.0, size=10, currentValue=10.0)
    assert not pos.resolved_loss


def test_open_position_is_not_a_loss():
    # Live market trading near zero must never be hidden.
    pos = Position(redeemable=False, curPrice=0.02, size=100)
    assert not pos.resolved_loss


def test_fifty_fifty_resolution_still_pays():
    pos = Position(redeemable=True, curPrice=0.5, size=10, currentValue=5.0)
    assert not pos.resolved_loss
