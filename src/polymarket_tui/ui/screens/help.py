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
| arrows | move; up/down also flow into adjacent panels (category bar, book, trades, search) |
| right or enter | open the selected row |
| left or escape | back |
| tab / shift+tab | cycle the screen's selector (category / timeframe / pane) |
| space | the contextual toggle (see below) |

space by screen: star an event or follow a trader (home, search,
watchlist, related), buy the selected outcome (market - priced at the
level under the cursor when the book is focused), toggle BUY/SELL
(order panel), show/hide rules (event; on market it's i), follow/unfollow
(trader profile).

left always steps out one level: order panel -> market -> previous screen;
expanded trades collapse before the screen closes.

## Going places

| Key | Action |
|-----|--------|
| / | search |
| p | portfolio (a top-level root like Home - drilling into a market keeps it as the parent) |
| w | watchlist |
| H or Home | home screen |
| A | auth / credentials |
| L | toggle DRY/LIVE (going live asks for confirmation; the mode persists) |
| ? | this help |
| q | quit |

## Extras where they matter

| Key | Where | Action |
|-----|-------|--------|
| o | home | cycle sort (24h volume / liquidity / ending / newest) |
| b / s | lists, event, market | order entry; on a home/watchlist row it
jumps straight into the market with the panel open |
| y / n | market | jump straight to the YES / NO book |
| down / up | market | step the cursor into the order book and back to the outcomes |
| right | market | step the cursor into the trades rail |
| a | market | expand the inline trades to full width (right opens the trader) |
| i | market | show/hide the rules rail (auto-shown on wide terminals) |
| c | market | comments in the chart strip |
| e | market | open the parent event |
| R | event, market | related markets (series siblings for dailies) |
| x | portfolio open-orders tab | cancel the highlighted order |
| r | anywhere | refresh |

## Order entry

On a market, space / b / enter open the buy form and s opens it to sell;
when the book is focused (down from the outcomes) the form is priced at the
level under the cursor. left (at the start of a field) or escape closes it.
b/s/space switch the side at any time, even while typing in the fields.

Price (focused first) and size; price is in CENTS ('33.4' = 33.4c). Leave
price empty for a market order at the touch. up/down bump by one tick or
share, shift+up/down by ten. Selling: enter a percentage ('50%') to sell
that fraction of your position - the held amount is shown in the panel.
tab hops fields, enter reviews, y places, esc steps back. ctrl+g cycles
TIF (GTC/FOK/FAK). The book stays live above the form.

The app never blocks an order the exchange would accept. Hard stops exist
only for orders that cannot succeed (closed market, bad tick, below minimum
size, price out of range, insufficient cash/shares). Anything else - far
off mid, large notional, rapid duplicate - is at most a yellow warning.

## Charts

Charts sit below/beside the prices they explain - history is context, not
the headline. The legend shows the latest price and the change over the
visible window; tab / shift+tab cycle the timeframe.

The header clock ticks in milliseconds, corrected against network time
(SNTP); "(sys)" means NTP was unreachable.

Search (/) has two result modes toggled with tab: MARKETS and TRADERS.
Arrows drive the visible list from the input; enter opens. In traders mode
the side pane previews the highlighted trader (value, top positions);
opening a profile shows full positions/activity, space follows them there.
The watchlist (w) keeps Events and Traders tabs. Market pages show your
position for that market under the outcome rows.

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

