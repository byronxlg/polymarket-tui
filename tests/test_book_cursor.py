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
from polymarket_tui.ui.widgets.book_panel import (
    CURSOR_BG,
    DEPTH,
    EXPAND_CHUNK,
    BookPanel,
)


def _book() -> OrderBook:
    return OrderBook.model_validate(
        {
            "bids": [{"price": "0.32", "size": "100"}, {"price": "0.31", "size": "50"}],
            "asks": [{"price": "0.34", "size": "80"}, {"price": "0.35", "size": "40"}],
        }
    )


def _deep_book(per_side: int = 30) -> OrderBook:
    """A book deeper than the default window: bids below 33c, asks above."""
    return OrderBook.model_validate(
        {
            "bids": [
                {"price": f"{0.33 - 0.001 * (i + 1):.3f}", "size": "100"}
                for i in range(per_side)
            ],
            "asks": [
                {"price": f"{0.33 + 0.001 * (i + 1):.3f}", "size": "100"}
                for i in range(per_side)
            ],
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


async def test_default_window_caps_depth_and_flags_hidden_levels() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        rendered: list = []
        original = book.update

        def spy(renderable="", *args, **kwargs):
            rendered.append(renderable)
            return original(renderable, *args, **kwargs)

        book.update = spy  # type: ignore[method-assign]
        book.update_book(_deep_book(30))
        await pilot.pause()
        kinds = [kind for kind, _ in book._levels]
        assert kinds.count("ask") == DEPTH
        assert kinds.count("bid") == DEPTH
        assert str(rendered[-1]).count("· 20 more") == 2  # hidden asks + bids


async def test_cursor_near_bottom_reveals_more_bids() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        book.focus()
        await pilot.pause()
        book.focus_top()  # pin the start: the first render centers on the mid
        # Walk to the last visible row; entering the margin reveals a chunk.
        for _ in range(len(book._levels) - 1):
            book.action_cursor(1)
        price_before = book.cursor_price
        assert len(book._levels) == DEPTH + DEPTH + EXPAND_CHUNK
        assert price_before is not None
        # The cursor stayed on the level it was on (rows append below).
        assert book._levels[book._cursor][1].price == price_before


async def test_cursor_near_top_reveals_more_asks_and_keeps_its_level() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        book.focus()
        await pilot.pause()
        book.focus_top()
        for _ in range(4):
            book.action_cursor(1)  # step below the margin (moving down never deepens asks)
        assert [kind for kind, _ in book._levels].count("ask") == DEPTH
        book.action_cursor(-1)  # to row 3 - still outside the margin
        price_before = book._levels[2][1].price  # where the next move lands
        book.action_cursor(-1)  # into the margin -> asks deepen
        kinds = [kind for kind, _ in book._levels]
        assert kinds.count("ask") == DEPTH + EXPAND_CHUNK
        # Prepended rows shifted the index; the cursor kept its price level.
        assert book._cursor == 2 + EXPAND_CHUNK
        assert book._levels[book._cursor][1].price == price_before


async def test_up_at_top_exits_only_once_all_asks_revealed() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        book.focus()
        await pilot.pause()
        posted: list = []
        original = book.post_message

        def spy(message):
            posted.append(message)
            return original(message)

        book.post_message = spy  # type: ignore[method-assign]
        book.focus_top()
        for _ in range(5):
            book.action_cursor(1)  # start a few rows below the top
        # Walk upward: expansions keep the cursor off row 0 until every ask
        # is visible, then row 0 is the deepest ask and up steps out.
        for _ in range(60):
            book.action_cursor(-1)
        assert any(isinstance(m, BookPanel.FocusAbove) for m in posted)
        kinds = [kind for kind, _ in book._levels]
        assert kinds.count("ask") == 30  # everything revealed on the way


async def test_reset_depth_restores_the_default_window() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        book.focus()
        await pilot.pause()
        for _ in range(len(book._levels) - 1):
            book.action_cursor(1)
        assert len(book._levels) > 2 * DEPTH
        book.reset_depth()
        book.update_book(_deep_book(30))  # outcome flip re-renders
        kinds = [kind for kind, _ in book._levels]
        assert kinds.count("ask") == DEPTH
        assert kinds.count("bid") == DEPTH


async def test_first_render_centers_cursor_on_the_best_ask() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        await pilot.pause()
        kind, level = book._levels[book._cursor]
        assert kind == "ask"
        assert level.price == 0.331  # best ask = the row hugging the mid


async def test_m_recenters_after_browsing_depth() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        book.focus()
        await pilot.pause()
        for _ in range(8):
            book.action_cursor(1)  # wander into the bids
        assert book._levels[book._cursor][0] == "bid"
        book.action_center()
        kind, level = book._levels[book._cursor]
        assert kind == "ask" and level.price == 0.331


async def test_outcome_reset_recenters_on_the_new_book() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        book.update_book(_deep_book(30))
        await pilot.pause()
        for _ in range(5):
            book.action_cursor(1)
        book.reset_depth()  # outcome flip
        book.update_book(_deep_book(30))
        assert book._levels[book._cursor][1].price == 0.331


async def test_book_prices_render_true_to_tick() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        book = app.query_one(BookPanel)
        rendered: list = []
        original = book.update

        def spy(renderable="", *args, **kwargs):
            rendered.append(renderable)
            return original(renderable, *args, **kwargs)

        book.update = spy  # type: ignore[method-assign]
        book.set_price_decimals(0)  # a 1c-tick market
        book.update_book(_book())  # bids 32/31c, asks 34/35c -> mid 33c
        await pilot.pause()
        text = str(rendered[-1])
        assert "34c" in text and "32c" in text
        assert "33.0c" not in text and "34.0c" not in text
        assert "mid 33c" in text  # whole-cent mid stays whole

        # A half-tick mid keeps one extra place instead of rounding.
        book.update_book(
            OrderBook.model_validate(
                {
                    "bids": [{"price": "0.32", "size": "10"}],
                    "asks": [{"price": "0.33", "size": "10"}],
                }
            )
        )
        assert "mid 32.5c" in str(rendered[-1])
