"""A status line must survive error text that looks like Rich markup.

The portfolio balance line rendered `Static.update(str)`, which parses Rich
console markup. An API 502's exception message embeds the raw HTML response
body - `PolyApiException[status_code=502, error_message=<!DOCTYPE html>...]` -
and its '[' raised MarkupError, crashing the whole app. The fix wraps the line
in rich.text.Text, which is never parsed as markup.
"""

from __future__ import annotations

import pytest
from rich.text import Text
from textual.app import App, ComposeResult
from textual.markup import MarkupError
from textual.widgets import Static


class _Host(App):
    def compose(self) -> ComposeResult:
        yield Static(id="balance-line")


# The exact string family that crashed: brackets + embedded angle-bracket HTML.
BAD = (
    "positions $186.20  |  mode LIVE  |  balance error: "
    "PolyApiException[status_code=502, error_message=<!DOCTYPE html>\n<html>]"
)


async def test_updating_with_a_bare_markup_string_crashes() -> None:
    """Locks the failure mode: the old code path still raises, so the Text
    wrapper below is load-bearing, not incidental."""
    app = _Host()
    async with app.run_test(size=(120, 5)):
        line = app.query_one("#balance-line", Static)
        with pytest.raises(MarkupError):
            line.update(BAD)


async def test_updating_with_a_text_wrapper_is_safe() -> None:
    app = _Host()
    async with app.run_test(size=(120, 5)):
        line = app.query_one("#balance-line", Static)
        line.update(Text(BAD))  # must not raise
        assert "502" in line.render().plain


# -- title lines carry API/user text and must render literally too -------------


def test_market_title_line_returns_text_even_with_bracketed_question():
    """A Gamma question like "Will X drop [before Y]?" must not reach the
    Static as a markup string. _title_line now returns a Text."""
    from rich.text import Text as RichText

    from polymarket_tui.models.market import Market
    from polymarket_tui.ui.screens.market import MarketPane

    market = Market.model_validate(
        {
            "question": "Will BTC dip [below $50k] in July?",
            "slug": "btc-dip",
            "clobTokenIds": '["1", "2"]',
            "outcomes": '["Yes", "No"]',
            "active": True,
            "closed": False,
        }
    )
    pane = object.__new__(MarketPane)  # skip Textual widget __init__
    pane._market = market
    pane._event = None
    line = pane._title_line()
    assert isinstance(line, RichText)
    assert "[below $50k]" in line.plain  # literal, not swallowed as markup


def test_user_title_line_returns_text_even_with_bracketed_name():
    from rich.text import Text as RichText

    from polymarket_tui.ui.screens.user import UserPane

    class _WL:
        def is_watched_user(self, _addr):
            return False

    class _App:
        watchlist = _WL()

    import unittest.mock as m

    pane = object.__new__(UserPane)  # skip Textual widget __init__
    pane._address = "0x" + "ab" * 20
    pane._trader_name = "trader[bracket]name"
    # _title_line reads self.app.watchlist; Widget.app is a read-only property,
    # so stub it on the class for the duration of the call.
    with m.patch.object(UserPane, "app", property(lambda self: _App())):
        line = pane._title_line()
    assert isinstance(line, RichText)
    assert "trader[bracket]name" in line.plain
