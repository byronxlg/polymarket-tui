"""Help screen: keybinding reference."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Markdown

from polymarket_tui.ui.widgets.app_header import AppHeader

HELP_TEXT = """\
# polymarket-tui

Browse, books, charts, search, watchlist, portfolio (p), trading.
Orders are dry-run (signed, not posted) unless POLYMARKET_EXECUTION_LIVE=1.

## Global

| Key | Action |
|-----|--------|
| / | search |
| H | home |
| w | watchlist |
| A | auth / credentials |
| ? | this help |
| q | quit |
| escape, left, < | back |

One scheme everywhere: arrows drive everything. up/down move (and move INTO
the widget above: category bar on home, chart inspect on event/market, the
search box on search), right/enter open, left/escape back. tab cycles the
screen's main selector (category, chart timeframe, or pane), h/l are tab
aliases, r refreshes, W stars.

## Home

| Key | Action |
|-----|--------|
| up (at top row) | focus category bar; left/right switch, down returns |
| tab / shift+tab | next / prev category |
| o | cycle sort (24h volume / liquidity / ending soonest / newest) |

The preview panel follows the highlighted (or mouse-hovered) row.

## Event

| Key | Action |
|-----|--------|
| tab or 1-6 | chart timeframe (1H 6H 1D 1W 1M ALL) |
| up (at top row) or x | inspect chart (left/right scrub, down/esc exit) |
| c | show/hide the multi-outcome chart |
| i | swap right pane: outcome preview <-> rules |
| R | related markets (series siblings, e.g. other days of a daily) |

## Market

| Key | Action |
|-----|--------|
| tab or 1-6 | chart timeframe |
| up or x | inspect chart (left/right scrub, down/esc exit) |
| t | flip order book YES/NO |
| b / s | open order entry below the book (BUY / SELL) |

Order entry: price + size only. Empty price = market order at the touch.
up/down bump the price one tick, tab hops between fields, enter reviews,
y places (esc edits). ctrl+g cycles TIF (GTC/FOK/FAK). The book stays
live above the form. Orders are dry-run unless LIVE mode is on.

Order book auto-refreshes every 3 seconds.

## Portfolio (p)

| Key | Action |
|-----|--------|
| tab | cycle positions / open orders / history |
| x | cancel highlighted open order |

The header clock ticks in milliseconds and is corrected against network time
(SNTP); "(sys)" after the time means NTP was unreachable and the system clock
is shown uncorrected.

Data: gamma-api.polymarket.com (metadata), clob.polymarket.com (books, history),
data-api.polymarket.com (positions, activity).
"""


class HelpScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("j,down", "scroll_help(3)", "down", show=False),
        Binding("k,up", "scroll_help(-3)", "up", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader("help")
        body = VerticalScroll(Markdown(HELP_TEXT), id="help-body")
        body.can_focus = False
        yield body
        yield Footer()

    def on_mount(self) -> None:
        self.title = "help"

    def action_scroll_help(self, amount: int) -> None:
        body = self.query_one("#help-body", VerticalScroll)
        body.scroll_relative(y=amount, animate=False)

