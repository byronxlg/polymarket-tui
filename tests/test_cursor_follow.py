"""CursorFollow: leading call goes through, bursts coalesce to one trailing call."""

from __future__ import annotations

from polymarket_tui.ui.follow import CursorFollow


class FakeWidget:
    def __init__(self) -> None:
        self.timers: list = []

    def set_timer(self, _delay: float, callback) -> None:
        self.timers.append(callback)

    def fire(self) -> None:
        pending, self.timers = self.timers, []
        for cb in pending:
            cb()


def test_leading_call_is_immediate() -> None:
    w, calls = FakeWidget(), []
    follow = CursorFollow(w, calls.append, interval=60.0)
    follow("a")
    assert calls == ["a"]
    assert w.timers == []


def test_burst_coalesces_to_latest() -> None:
    w, calls = FakeWidget(), []
    follow = CursorFollow(w, calls.append, interval=60.0)
    for slug in "abcdef":
        follow(slug)
    assert calls == ["a"]  # leading only; the burst is pending
    assert len(w.timers) == 1  # one trailing timer, not one per call
    w.fire()
    assert calls == ["a", "f"]  # only the latest pending value renders


def test_trailing_flush_without_pending_is_noop() -> None:
    w, calls = FakeWidget(), []
    follow = CursorFollow(w, calls.append, interval=60.0)
    follow("a")
    follow("b")
    w.fire()
    w.fire()  # stray extra flush
    assert calls == ["a", "b"]
