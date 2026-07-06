"""Help screen: keybinding reference."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Markdown

from polymarket_tui.ui.widgets.app_footer import AppFooter
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

The footer keeps the two vocabularies apart: contextual keys for the
current screen on the left; Global navigation (blue, Capitalized - Quit,
Search, Portfolio, Watched, Back, Help, Refresh) on the right. Global
letter keys are capitals (W, P, Q, R, H, A, L, T); lowercase letters are
always contextual.

space by screen: star an event or follow a trader (home, search,
watchlist, related), open the buy form on a market outcome or order from
the book level (market), toggle BUY/SELL (order panel), show/hide rules
(event; on market it's i), follow/unfollow (trader profile). Pick the
outcome with the arrows or y/n; right on an outcome flows into the book.

left always steps out one level: order panel -> market -> previous screen;
expanded trades collapse before the screen closes.

## Going places

| Key | Action |
|-----|--------|
| / | search |
| P | portfolio (a top-level root like Home - drilling into a market keeps it as the parent) |
| W | watchlist |
| H or Home | home screen |
| A | auth / credentials |
| L | toggle DRY/LIVE (going live asks for confirmation; the mode persists) |
| T | toggle condensed/spacious density (spacious: two-line rows with market metadata; persists) |
| ? | this help |
| Q | quit |

## Extras where they matter

| Key | Where | Action |
|-----|-------|--------|
| o | home | cycle sort (24h volume / liquidity / ending / newest) |
| b / s | lists, event, market | order entry; on a home/watchlist row it
jumps straight into the market with the panel open |
| y / n | market | jump straight to the YES / NO book |
| a | market | expand the inline trades to full width (right opens the trader) |
| i | market | show/hide the rules rail (auto-shown on wide terminals) |
| c | market | comments in the chart strip |
| e | market | open the parent event |
| r | event, market | related markets pop-out (series siblings for dailies); esc closes |
| space | market order book | order prefilled from the level (ask -> BUY, bid -> SELL) |
| x | market book / portfolio orders | cancel a resting order (details shown, enter confirms) |
| s | portfolio positions | cash out: sell form prefilled with the full position at the bid |
| R | any data screen | refresh what you're looking at (also refetches balances and flags) |

List rows carry flags: * watched, o resting order, + position held (home
and event outcome lists; holdings show in observer mode too).

## Order entry

space or enter on an outcome row opens the buy form; left (at the start of
a field) or escape closes it. b/s/space switch the side at any time, even
while typing in the fields.

Price (focused first) and size; price is in CENTS ('33.4' = 33.4c). Leave
price empty for a market order at the touch. up/down bump by one tick or
share, shift+up/down by ten. Selling: the form opens prefilled with your
full position at the live bid (s, enter, enter cashes out) - trim the
size, bump the price, or type a percentage ('50%') to sell that fraction;
the held amount is shown in the panel.
tab hops fields, enter reviews, a second enter places (the strip arms
after a beat, so a held-down enter cannot), esc steps back. ctrl+g cycles
TIF (GTC/FOK/FAK). The form sits top right; the book stays live beside it.

The app never blocks an order the exchange would accept. Hard stops exist
only for orders that cannot succeed (closed market, bad tick, below minimum
size, price out of range, insufficient cash/shares). Anything else - far
off mid, large notional, rapid duplicate - is at most a yellow warning.

## Chart inspect

Charts sit below/beside the prices they explain - history is context, not
the headline. On an event, down past the last outcome row enters chart
inspect: left/right scrub through time (shift for big steps), the legend
shows values at the crosshair, up/down/esc exit. On a market, down past the
last outcome row instead cursors into the order book (space orders from a
level, x cancels a resting order there); the chart is display-only.

The header clock ticks in milliseconds, corrected against network time
(SNTP); "(sys)" means NTP was unreachable.

Search (/) has two result modes toggled with tab: MARKETS and TRADERS.
down moves from the input into the result list (up at the top, or left/esc,
returns); enter opens the highlighted result from either side; space in the
list stars an event or follows a trader. In traders mode the side pane
previews the highlighted trader (value, top positions); opening a profile
shows full positions/activity, space follows them there.
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
        yield AppFooter()

    def on_mount(self) -> None:
        self.title = "help"

    def action_scroll_help(self, amount: int) -> None:
        body = self.query_one("#help-body", VerticalScroll)
        body.scroll_relative(y=amount, animate=False)

