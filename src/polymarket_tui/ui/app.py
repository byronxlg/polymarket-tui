"""The Textual application: screen stack, shared clients, global bindings."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from polymarket_tui.api.clob import ClobPublicClient
from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.api.data import DataApiClient
from polymarket_tui.api.gamma import GammaClient
from polymarket_tui.core.config import Settings, get_settings
from polymarket_tui.models.market import Event, Market
from polymarket_tui.services.orders import OrderService
from polymarket_tui.services.portfolio import PortfolioService
from polymarket_tui.state.watchlist import Watchlist
from polymarket_tui.ui.screens.auth import AuthScreen
from polymarket_tui.ui.screens.event import EventScreen
from polymarket_tui.ui.screens.help import HelpScreen
from polymarket_tui.ui.screens.home import HomeScreen
from polymarket_tui.ui.screens.market import MarketScreen
from polymarket_tui.ui.screens.portfolio import PortfolioScreen
from polymarket_tui.ui.screens.search import SearchScreen
from polymarket_tui.ui.screens.watchlist import WatchlistScreen


class PolymarketApp(App):
    TITLE = "polymarket-tui"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("q", "quit", "quit", priority=True),
        Binding("slash", "search", "search"),
        Binding("H", "home", "home", show=False, key_display="H"),
        Binding("w", "watchlist", "watchlist"),
        Binding("p", "portfolio", "portfolio"),
        Binding("A", "auth", "auth", show=False, key_display="A"),
        Binding("question_mark", "help", "help", key_display="?"),
        Binding("left", "nav_back", "back", show=False),
        Binding("less_than_sign", "nav_back", "back", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()
        self.gamma = GammaClient()
        self.clob = ClobPublicClient()
        self.data = DataApiClient()
        self.authed: AuthedClobClient | None = (
            AuthedClobClient(self.settings) if self.settings.can_auth else None
        )
        self.portfolio = PortfolioService(self.settings, self.data, self.authed)
        self.orders = OrderService(self.settings, self.authed)
        self.watchlist = Watchlist()

    def get_default_screen(self) -> HomeScreen:
        return HomeScreen()

    async def on_unmount(self) -> None:
        await self.gamma.aclose()
        await self.clob.aclose()
        await self.data.aclose()

    # -- navigation helpers (screens call these) ---------------------------

    def open_event(self, event: Event) -> None:
        """Open an event; binary events go straight to the market screen."""
        if event.is_binary and event.top_market is not None:
            self.push_screen(MarketScreen(event.top_market, event))
        else:
            self.push_screen(EventScreen(event))

    def open_market(self, market: Market, event: Event | None = None) -> None:
        self.push_screen(MarketScreen(market, event))

    # -- global actions ------------------------------------------------------

    def _push_unless_current(self, screen_cls: type, factory) -> None:
        if not isinstance(self.screen, screen_cls):
            self.push_screen(factory())

    def action_search(self) -> None:
        self._push_unless_current(SearchScreen, SearchScreen)

    def action_watchlist(self) -> None:
        self._push_unless_current(WatchlistScreen, WatchlistScreen)

    def reconfigure(self, settings: Settings) -> None:
        """Swap credentials at runtime (auth screen). Rebuilds the authed stack."""
        self.settings = settings
        self.authed = AuthedClobClient(settings) if settings.can_auth else None
        self.portfolio = PortfolioService(settings, self.data, self.authed)
        self.orders = OrderService(settings, self.authed)

    def action_auth(self) -> None:
        self._push_unless_current(AuthScreen, AuthScreen)

    def action_portfolio(self) -> None:
        if not self.settings.can_read_portfolio:
            self.notify(
                "Portfolio needs a funder address - press A to authenticate", severity="warning"
            )
            return
        self._push_unless_current(PortfolioScreen, PortfolioScreen)

    def action_help(self) -> None:
        self._push_unless_current(HelpScreen, HelpScreen)

    def action_home(self) -> None:
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def action_nav_back(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
