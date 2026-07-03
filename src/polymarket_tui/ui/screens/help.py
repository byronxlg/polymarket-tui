"""Help screen: keybinding reference."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown

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

One scheme everywhere: arrows/j/k move, enter/right/> open, escape/left/< back,
tab cycles the screen's main selector (category, chart timeframe, or pane),
h/l work as tab aliases, r refreshes, W stars.

## Home

| Key | Action |
|-----|--------|
| tab / shift+tab | next / prev category |
| o | cycle sort (24h volume / liquidity / ending soonest / newest) |

The preview panel follows the highlighted (or mouse-hovered) row.

## Event

| Key | Action |
|-----|--------|
| tab or 1-6 | chart timeframe (1H 6H 1D 1W 1M ALL) |
| x | inspect chart (crosshair; left/right scrub, esc exit) |
| c | show/hide the multi-outcome chart |
| i | swap right pane: outcome preview <-> rules |

## Market

| Key | Action |
|-----|--------|
| tab or 1-6 | chart timeframe |
| x | inspect chart (crosshair; left/right scrub, esc exit) |
| t | flip order book YES/NO |
| b / s | buy / sell order form |

Order book auto-refreshes every 3 seconds.

## Portfolio (p)

| Key | Action |
|-----|--------|
| tab | cycle positions / open orders / history |
| x | cancel highlighted open order |

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
        yield Header()
        body = VerticalScroll(Markdown(HELP_TEXT), id="help-body")
        body.can_focus = False
        yield body
        yield Footer()

    def on_mount(self) -> None:
        self.title = "help"

    def action_scroll_help(self, amount: int) -> None:
        body = self.query_one("#help-body", VerticalScroll)
        body.scroll_relative(y=amount, animate=False)
