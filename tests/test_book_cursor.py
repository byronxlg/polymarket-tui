"""Focusing the order book draws the row cursor; blurring hides it.

Behavioural guard for the cursor-on-focus fix. In the real terminal the cursor
was drawn from `has_focus`, which is not yet True inside the `on_focus` that
triggers the first render, so arrowing into the book showed no cursor until a
second keypress (landing on row 1). The fix tracks focus in `_focused`, set
synchronously in on_focus/on_blur. The headless harness sets `has_focus`
before on_focus, so it cannot reproduce that exact timing - this asserts the
observable contract (cursor follows focus state), which the live journey
review confirmed end to end.
"""

from __future__ import annotations

from textual.app import App, ComposeResult

from polymarket_tui.models.market import OrderBook
from polymarket_tui.ui.widgets.book_panel import CURSOR_BG, BookPanel


def _book() -> OrderBook:
    return OrderBook.model_validate(
        {
            "bids": [{"price": "0.32", "size": "100"}, {"price": "0.31", "size": "50"}],
            "asks": [{"price": "0.34", "size": "80"}, {"price": "0.35", "size": "40"}],
        }
    )


class _Host(App):
    def compose(self) -> ComposeResult:
        yield BookPanel(id="book")


def _draws_cursor(text) -> bool:
    return any(CURSOR_BG in str(span.style) for span in text.spans)


async def test_cursor_draws_on_first_focus() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        # The lone focusable widget auto-focuses on mount; start from unfocused
        # so the first focus below is the one under test.
        app.set_focus(None)
        await pilot.pause()

        # Capture the exact renderable each _render_book hands to update().
        rendered: list = []
        original = book.update

        def spy(renderable="", *args, **kwargs):
            rendered.append(renderable)
            return original(renderable, *args, **kwargs)

        book.update = spy  # type: ignore[method-assign]

        book.update_book(_book())
        assert rendered, "book did not render"
        assert not _draws_cursor(rendered[-1])  # not focused yet -> no cursor

        book.focus()
        await pilot.pause()
        # The render triggered by focus itself must already show the cursor -
        # no second keypress needed.
        assert _draws_cursor(rendered[-1])

        app.set_focus(None)
        await pilot.pause()
        assert not _draws_cursor(rendered[-1])  # blur hides the cursor again
