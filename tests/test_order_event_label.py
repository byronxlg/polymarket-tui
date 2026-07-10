"""The /ws/user own-order toast: filled, partly filled, or resting?

This is the line that answers "did my sell go through, or is it sitting on the
book?". It reads size_matched, not original_size: a LIVE order that partly
filled is both a fill and a resting order, and quoting the original size alone
announced a 100-share sell that filled 40 as "Order resting: SELL 100 Yes".
"""

from __future__ import annotations

from polymarket_tui.models.ws import UserOrderMessage
from polymarket_tui.ui.widgets.order_details import order_event_label


def msg(**overrides) -> UserOrderMessage:
    base = dict(
        side="SELL",
        outcome="Yes",
        price="0.334",
        original_size="100",
        size_matched="0",
        status="LIVE",
    )
    base.update(overrides)
    return UserOrderMessage(**base)


def test_resting_with_no_fill_says_nothing_filled():
    assert order_event_label(msg()) == "Resting on the book: SELL 100 Yes @ 33.4c - nothing filled"


def test_partly_filled_live_order_reports_both_halves():
    label = order_event_label(msg(size_matched="40"))
    assert label == "Partly filled: SELL 100 Yes @ 33.4c - 40 filled, 60 resting"


def test_partly_filled_never_reads_as_a_plain_resting_order():
    """The regression this whole change exists to prevent."""
    label = order_event_label(msg(size_matched="40"))
    assert not label.startswith("Resting")
    assert "40" in label


def test_fully_matched_order_reads_as_filled():
    assert order_event_label(msg(size_matched="100", status="MATCHED")) == (
        "Filled: SELL 100 Yes @ 33.4c"
    )


def test_cancel_of_a_partly_filled_order_names_the_filled_part():
    label = order_event_label(msg(size_matched="40", status="CANCELED"))
    assert label == "Canceled: SELL 60 Yes @ 33.4c (40 of 100 had filled)"


def test_cancel_of_an_untouched_order_names_the_whole_size():
    assert order_event_label(msg(status="CANCELED")) == "Canceled: SELL 100 Yes @ 33.4c"


def test_fractional_sizes_survive_a_percentage_sell():
    label = order_event_label(msg(original_size="12.5", size_matched="2.5"))
    assert "2.5 filled, 10 resting" in label


def test_unknown_status_falls_back_without_crashing():
    assert order_event_label(msg(status="")).startswith("Order updated: SELL 100 Yes")


def test_garbage_sizes_do_not_raise():
    assert order_event_label(msg(original_size="", size_matched="abc"))
