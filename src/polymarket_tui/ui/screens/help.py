"""Help screen: keybinding reference."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown

HELP_TEXT = """\
# polymarket-tui

Read-only demo build: browse, books, charts, search, watchlist.

## Global

| Key | Action |
|-----|--------|
| / | search |
| H | home |
| w | watchlist |
| ? | this help |
| q | quit |
| escape | back |

## Tables

| Key | Action |
|-----|--------|
| j / k, arrows | move |
| enter | open |
| W | toggle watchlist |
| r | refresh |

## Home

| Key | Action |
|-----|--------|
| o | cycle sort (24h volume / liquidity / ending soonest / newest) |
| [ / ] | prev / next category |

## Market

| Key | Action |
|-----|--------|
| t | flip order book YES/NO |
| 1-6 | chart interval (1H 6H 1D 1W 1M ALL) |

Order book auto-refreshes every 3 seconds.

Data: gamma-api.polymarket.com (metadata), clob.polymarket.com (books, history).
"""


class HelpScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="help-body"):
            yield Markdown(HELP_TEXT)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "help"
