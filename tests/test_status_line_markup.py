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
