"""NavHost drill: the inverted event-parent segment left by `e` collapses.

`e` opens a market's parent event as a drill CHILD, so a market reached
without its event (a Portfolio position, a trader's trade) leaves an inverted
[.., market, event] segment in the trail. Selecting a market from that event
must reparent to [.., event, market] - the plain event -> market layout - and
never step focus back to the market so it renders as a 30% YES/NO strip while
the event fills 70% (Byron, 2026-07-08).
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from polymarket_tui.ui.screens.nav_host import NavHost
from polymarket_tui.ui.widgets.app_footer import AppFooter
from polymarket_tui.ui.widgets.app_header import AppHeader


class FakePane(Vertical):
    """A drill pane stand-in: carries a drill_key and answers NavHost's hooks
    without pulling in a real screen's live services."""

    def __init__(self, kind: str | None, slug: str, **kwargs) -> None:
        super().__init__(**kwargs)
        if kind is not None:
            self.drill_key = (kind, slug)
        self.header_title = f"{kind}:{slug}"
        self.tier: str | None = None

    def set_tier(self, tier: str) -> None:
        self.tier = tier

    def focus_inner(self) -> None:
        pass


class _NavHost(NavHost):
    """NavHost rooted on a fake pane so the test needs no live services.

    Mirrors NavHost.compose exactly but swaps HomePane (which fetches on
    mount) for a keyless FakePane, matching Home/Portfolio's real absence of
    a drill_key."""

    def compose(self) -> ComposeResult:
        yield AppHeader("root")
        yield Static(id="nav-crumbs")
        root = FakePane(None, "root")
        root.add_class("nav-pane")
        self._panes = [root]
        self._crumbs = ["Home"]
        with Horizontal(id="nav-viewport"):
            yield root
        yield AppFooter()


class Host(App):
    def on_mount(self) -> None:
        self.push_screen(_NavHost())


def _kinds(host: NavHost) -> list[str | None]:
    return [getattr(p, "drill_key", (None,))[0] for p in host._panes]


def _slugs(host: NavHost) -> list[str]:
    return [getattr(p, "drill_key", (None, None))[1] for p in host._panes]


async def _host(pilot) -> NavHost:
    await pilot.pause()
    return pilot.app.screen  # the pushed _NavHost


async def test_reselecting_market_from_e_event_reparents() -> None:
    """Portfolio -> market -> e (event) -> re-select that same market.

    The stale market is dropped and the fresh one takes the 70% slot with
    the event as its 30% parent, instead of the market stranding at 30%."""
    async with Host().run_test(size=(160, 40)) as pilot:
        host = await _host(pilot)
        host.drill(FakePane("market", "A"), "A")  # from a position (no event)
        await pilot.pause()
        host.drill(FakePane("event", "E"), "E", solo=True)  # `e`, full width
        await pilot.pause()
        assert _kinds(host) == [None, "market", "event"]
        assert (host._focus, host._left) == (2, 2)  # event alone, full

        market = FakePane("market", "A")
        host.drill(market, "A")  # select the same market from the event
        await pilot.pause()

        assert _kinds(host) == [None, "event", "market"]  # orphan market gone
        assert _slugs(host) == [None, "E", "A"]  # keyless root, event, market
        assert (host._focus, host._left) == (2, 1)  # event 30% | market 70%
        assert market.tier == "medium"  # the market, not a YES/NO strip
        assert host._panes[1].tier == "compact"  # the event is the context


async def test_selecting_other_market_from_e_event_reparents() -> None:
    """A different row from the `e` event also collapses the orphan market."""
    async with Host().run_test(size=(160, 40)) as pilot:
        host = await _host(pilot)
        host.drill(FakePane("market", "A"), "A")
        await pilot.pause()
        host.drill(FakePane("event", "E"), "E", solo=True)
        await pilot.pause()

        host.drill(FakePane("market", "B"), "B")  # a sibling outcome
        await pilot.pause()

        assert _kinds(host) == [None, "event", "market"]
        assert _slugs(host) == [None, "E", "B"]  # no [.., A, E, B] orphan
        assert (host._focus, host._left) == (2, 1)


async def test_plain_event_to_market_is_unchanged() -> None:
    """The good flow (event as parent, drill a market) keeps its layout."""
    async with Host().run_test(size=(160, 40)) as pilot:
        host = await _host(pilot)
        host.drill(FakePane("event", "E"), "E")
        await pilot.pause()
        market = FakePane("market", "A")
        host.drill(market, "A")
        await pilot.pause()

        assert _kinds(host) == [None, "event", "market"]
        assert (host._focus, host._left) == (2, 1)
        assert market.tier == "medium"


async def test_e_back_to_parent_event_still_steps_back() -> None:
    """event -> market, then `e`: still a plain step back up to the parent
    event beside the market (no reparent, no remount)."""
    async with Host().run_test(size=(160, 40)) as pilot:
        host = await _host(pilot)
        host.drill(FakePane("event", "E"), "E")
        await pilot.pause()
        host.drill(FakePane("market", "A"), "A")
        await pilot.pause()

        host.drill(FakePane("event", "E"), "E", solo=True)  # `e` on the market
        await pilot.pause()

        assert _kinds(host) == [None, "event", "market"]  # trail untouched
        assert (host._focus, host._left) == (1, 1)  # focus back on the event


@pytest.mark.parametrize(
    "kinds,focus,new_key,expected",
    [
        (["market", "event"], 1, ("market", "A"), True),  # inverted segment
        ([None, "market", "event"], 2, ("market", "A"), True),
        ([None, "event", "market"], 1, ("market", "A"), False),  # normal trail
        (["market", "event"], 1, ("event", "E"), False),  # drilling an event
        ([None, "event"], 1, ("market", "A"), False),  # parent is not a market
        (["market", "event"], 1, None, False),  # keyless pane
    ],
)
def test_is_inverted_event_parent(kinds, focus, new_key, expected) -> None:
    assert NavHost._is_inverted_event_parent(kinds, focus, new_key) is expected
