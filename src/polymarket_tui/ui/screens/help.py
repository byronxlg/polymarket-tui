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

Browse, books, charts, search, watchlist, portfolio, trading.
Orders are dry-run (signed, never posted) unless LIVE mode is enabled.

## The core keys

| Key | Action |
|-----|--------|
| arrows | move; up/down also flow into adjacent panels (category bar, chart, search box) |
| right or enter | open the selected row |
| left or escape | back |
| tab / shift+tab | cycle the screen's selector (category / timeframe / pane) |
| space | the contextual toggle (see below) |

space by screen: star an event (home, search, watchlist, related),
flip the YES/NO book (market), show/hide rules (event).

## Going places

| Key | Action |
|-----|--------|
| / | search |
| p | portfolio |
| w | watchlist |
| H or Home | home screen |
| A | auth / credentials |
| ? | this help |
| q | quit |

## Extras where they matter

| Key | Where | Action |
|-----|-------|--------|
| o | home | cycle sort (24h volume / liquidity / ending / newest) |
| b / s | market | order entry below the live book (BUY / SELL) |
| y / n | market | jump straight to the YES / NO book |
| a / c | market | live trades feed / comments below the chart |
| R | event, market | related markets (series siblings for dailies) |
| x | portfolio open-orders tab | cancel the highlighted order |
| r | anywhere | refresh |

## Order entry

Price (focused first) and size; price is in CENTS ('33.4' = 33.4c). Leave
price empty for a market order at the touch. up/down bump by one tick or
share, shift+up/down by ten. Selling: enter a percentage ('50%') to sell
that fraction of your position - the held amount is shown in the panel.
tab hops fields, enter reviews, y places, esc steps back. ctrl+g cycles
TIF (GTC/FOK/FAK). The book stays live above the form.

## Chart inspect

Charts sit below/beside the prices they explain - history is context, not
the headline. On an event, down past the last outcome row enters chart
inspect; on a market, up enters it. left/right scrub through time (shift
for big steps), the legend shows values at the crosshair, up/down/esc exit.

The header clock ticks in milliseconds, corrected against network time
(SNTP); "(sys)" means NTP was unreachable.

Data: gamma-api.polymarket.com, clob.polymarket.com, data-api.polymarket.com.
"""

class HelpScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("down", "scroll_help(3)", "down", show=False),
        Binding("up", "scroll_help(-3)", "up", show=False),
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

