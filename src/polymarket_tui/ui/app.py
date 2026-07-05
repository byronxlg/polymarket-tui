"""The Textual application: screen stack, shared clients, global bindings."""

from __future__ import annotations

from rich.text import Text
from textual.app import App
from textual.binding import Binding

from polymarket_tui.api.clob import ClobPublicClient
from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.api.data import DataApiClient
from polymarket_tui.api.gamma import GammaClient
from polymarket_tui.api.ws import UserChannel
from polymarket_tui.core.auth import derive_l2_creds
from polymarket_tui.core.config import Mode, Settings, get_settings
from polymarket_tui.models.market import Event, Market
from polymarket_tui.models.ws import UserOrderMessage, UserTradeMessage
from polymarket_tui.services.orders import OrderService, ReconcileTarget
from polymarket_tui.services.portfolio import PortfolioService
from polymarket_tui.state.prefs import load_density, save_density
from polymarket_tui.state.watchlist import Watchlist
from polymarket_tui.ui.screens.auth import AuthScreen
from polymarket_tui.ui.screens.event import EventPane
from polymarket_tui.ui.screens.help import HelpScreen
from polymarket_tui.ui.screens.market import MarketPane
from polymarket_tui.ui.screens.nav_host import NavHost
from polymarket_tui.ui.screens.portfolio import PortfolioPane
from polymarket_tui.ui.screens.related import RelatedPane
from polymarket_tui.ui.screens.search import SearchScreen
from polymarket_tui.ui.screens.user import UserPane
from polymarket_tui.ui.screens.watchlist import WatchlistPane
from polymarket_tui.ui.theme import AMBER, BLUE, DOWN, PMTUI_THEME, UP
from polymarket_tui.ui.widgets.confirm_modal import ConfirmModal


class PolymarketApp(App):
    TITLE = "polymarket-tui"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("q", "quit", "quit", priority=True),
        Binding("slash", "search", "search"),
        Binding("H", "home", "home", show=False, key_display="H"),
        Binding("home", "home", "home", show=False),
        Binding("w", "watchlist", "watchlist", show=False),
        Binding("p", "portfolio", "portfolio"),
        Binding("A", "auth", "auth", show=False, key_display="A"),
        Binding("L", "toggle_live", "live", show=False, key_display="L"),
        Binding("T", "toggle_density", "layout", show=False, key_display="T"),
        Binding("question_mark", "help", "help", key_display="?"),
        Binding("left", "nav_back", "back", show=False),
        Binding("less_than_sign", "nav_back", "back", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(PMTUI_THEME)
        self.theme = "pmtui"
        # Layout density: the app root carries a density-<name> class so
        # app.tcss can restyle spacing declaratively (spacious block there).
        self.density = load_density()
        self.add_class(f"density-{self.density}")
        self.ntp_offset: float | None = None
        self.username: str | None = None
        self.account_status = Text("loading account...", style="dim")
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
        # A status-unknown live post to reconcile against Open Orders (issue #3).
        self.reconcile_target: ReconcileTarget | None = None
        # Live own-order/fill updates over the /ws/user socket (issue #1).
        self.user_channel: UserChannel | None = None

    def get_default_screen(self) -> NavHost:
        return NavHost()

    def notify(self, message: str, **kwargs) -> None:
        """Toasts render literally by default: API/validation errors carry
        [bracketed] text that Textual would parse as markup and crash the
        whole app on (trader search, 2026-07-05)."""
        kwargs.setdefault("markup", False)
        super().notify(message, **kwargs)

    def on_mount(self) -> None:
        self.run_worker(self._refresh_ntp_offset(), group="ntp", exclusive=True)
        self.set_interval(900, self._schedule_ntp_refresh)
        self.refresh_account_status()
        self.set_interval(60, self.refresh_account_status)
        self.start_user_channel()
        if self.settings.mode is Mode.TRADER_LIVE:
            # The persisted flag restored a LIVE session - say so loudly.
            self.notify(
                "Started LIVE (restored from last session) - orders post for real. L drops to DRY.",
                severity="warning",
                timeout=10,
            )

    def start_user_channel(self) -> None:
        """Connect the authenticated /ws/user socket for live own-order updates."""
        if not self.settings.can_auth:
            return
        self.run_worker(self._start_user_channel(), group="user-ws", exclusive=True)

    async def _start_user_channel(self) -> None:
        if self.user_channel is not None:
            await self.user_channel.stop()
            self.user_channel = None
        creds = await derive_l2_creds(self.settings)
        if not creds:
            return
        self.user_channel = UserChannel(creds, self._on_user_event)
        self.user_channel.start()

    def _on_user_event(self, kind: str, msg: object) -> None:
        """Own order/fill arrived over the socket: toast it and refresh open orders."""
        if kind == "order" and isinstance(msg, UserOrderMessage):
            verb = {"LIVE": "resting", "CANCELED": "canceled", "MATCHED": "filled"}.get(
                msg.status, msg.status.lower()
            )
            self.notify(
                f"Order {verb}: {msg.side} {msg.original_size} {msg.outcome} @ "
                f"{float(msg.price) * 100:.1f}c",
                timeout=6,
            )
        elif kind == "trade" and isinstance(msg, UserTradeMessage):
            self.notify(
                f"Fill: {msg.side} {msg.size} {msg.outcome} @ {float(msg.price) * 100:.1f}c",
                timeout=6,
            )
        else:
            return
        self.portfolio.invalidate()
        # Refresh the open-orders tab live if a portfolio pane is mounted.
        host = self._nav_host()
        if host is not None:
            for pane in host.query(PortfolioPane):
                pane.load_orders()

    def _schedule_ntp_refresh(self) -> None:
        self.run_worker(self._refresh_ntp_offset(), group="ntp", exclusive=True)

    async def _refresh_ntp_offset(self) -> None:
        import asyncio

        from polymarket_tui.core.ntp import sntp_offset

        offset = await asyncio.to_thread(sntp_offset)
        if offset is not None:
            self.ntp_offset = offset

    def refresh_account_status(self) -> None:
        self.run_worker(self._refresh_account_status(), group="account", exclusive=True)

    async def _refresh_account_status(self) -> None:
        """Build the header account strip: user, cash, portfolio value, mode."""
        settings = self.settings
        mode_style = {"RO": "dim", "OBS": BLUE, "DRY": AMBER, "LIVE": f"bold {DOWN}"}
        out = Text()
        if not settings.can_read_portfolio:
            out.append("not signed in - press A", style="dim")
            self.account_status = out
            return
        if self.username is None:
            try:
                self.username = await self.gamma.public_profile_name(settings.polymarket_funder)
            except Exception:
                self.username = None
        funder = settings.polymarket_funder
        display_name = self.username or f"{funder[:6]}...{funder[-4:]}"
        out.append(display_name, style="bold")
        try:
            if self.authed is not None:
                cash = await self.portfolio.usdc_balance()
                if cash is not None:
                    out.append("  cash ", style="dim")
                    out.append(f"${cash:,.2f}", style=UP)
            value = await self.portfolio.portfolio_value()
            if value is not None:
                out.append("  pf ", style="dim")
                out.append(f"${value:,.2f}", style=UP)
        except Exception:
            out.append("  (balances unavailable)", style="dim")
        mode = settings.mode.value
        out.append("  ")
        out.append(mode, style=mode_style[mode])
        self.account_status = out

    async def on_unmount(self) -> None:
        if self.user_channel is not None:
            await self.user_channel.stop()
        await self.gamma.aclose()
        await self.clob.aclose()
        await self.data.aclose()

    # -- navigation helpers (screens call these) ---------------------------

    def _nav_host(self) -> NavHost | None:
        base = self.screen_stack[0]
        return base if isinstance(base, NavHost) else None

    def _drill(self, pane, crumb: str, reuse: bool = True) -> None:
        """Open `pane` as a drill child in NavHost, popping any overlay first.

        Opens that originate from an overlay screen (watchlist, search,
        portfolio) are unrelated to whatever drill trail was open before -
        reset to the root and show the new pane alone at full width; the
        home list only appears as the parent after stepping out (left/esc).
        """
        host = self._nav_host()
        if host is None:
            return
        from_overlay = len(self.screen_stack) > 1
        while len(self.screen_stack) > 1:
            self.pop_screen()
        if from_overlay:
            host.reset_to_root()
        host.drill(pane, crumb, reuse=reuse, solo=from_overlay)

    def open_event(self, event: Event) -> None:
        """Open an event; binary events go straight to the market pane."""
        if event.is_binary and event.top_market is not None:
            self.open_market(event.top_market, event)
            return
        self._drill(EventPane(event), event.title)

    def open_market(
        self, market: Market, event: Event | None = None, order_side: str | None = None
    ) -> None:
        # A pending order side must reach a fresh pane - skip child reuse then.
        self._drill(
            MarketPane(market, event, order_side=order_side),
            market.display_title,
            reuse=order_side is None,
        )

    def quick_order(self, event: Event, side: str) -> None:
        """b/s on a list row: jump straight to the tradable market with the
        order panel armed (targeted traders skip the event screen)."""
        if not self.settings.can_auth:
            self.notify(
                "Trading needs a private key + funder - press A to authenticate",
                severity="warning",
            )
            return
        top = event.top_market
        if event.is_binary and top is not None:
            self.open_market(top, event, order_side=side)
        else:
            self.open_event(event)
            self.notify("Multi-outcome event - pick an outcome, then b/s", timeout=4)

    def open_related(self, event: Event) -> None:
        self._drill(RelatedPane(event), "related")

    def open_user(self, address: str, name: str) -> None:
        self._drill(UserPane(address, name), name)

    # -- global actions ------------------------------------------------------

    def _push_unless_current(self, screen_cls: type, factory) -> None:
        if not isinstance(self.screen, screen_cls):
            self.push_screen(factory())

    def action_search(self) -> None:
        self._push_unless_current(SearchScreen, SearchScreen)

    def action_watchlist(self) -> None:
        """'w': switch the drill root to the watchlist (same top level as Home)."""
        host = self._nav_host()
        if host is None:
            return
        while len(self.screen_stack) > 1:
            self.pop_screen()
        if isinstance(host.root_pane, WatchlistPane):
            host.reset_to_root()
        else:
            host.set_root(WatchlistPane(), "Watched")

    def reconfigure(self, settings: Settings) -> None:
        """Swap credentials at runtime (auth screen). Rebuilds the authed stack."""
        self.settings = settings
        self.authed = AuthedClobClient(settings) if settings.can_auth else None
        self.portfolio = PortfolioService(settings, self.data, self.authed)
        self.orders = OrderService(settings, self.authed)
        self.username = None
        self.refresh_account_status()
        self.start_user_channel()  # reconnect /ws/user with the new creds

    def action_auth(self) -> None:
        self._push_unless_current(AuthScreen, AuthScreen)

    def action_toggle_live(self) -> None:
        """DRY/LIVE flip: going live is confirmed, dropping to DRY is instant.
        The choice persists with the saved credentials (Byron, 2026-07-05);
        a session that starts LIVE announces it on mount."""
        if not self.settings.can_auth:
            self.notify(
                "Trading needs a private key + funder - press A to authenticate",
                severity="warning",
            )
            return
        from polymarket_tui.core.credstore import save_execution_live

        if self.settings.mode is Mode.TRADER_LIVE:
            self.reconfigure(
                self.settings.model_copy(update={"polymarket_execution_live": False})
            )
            save_execution_live(False)
            self.notify("DRY - orders are signed but never posted", timeout=4)
            return
        body = Text()
        body.append("Orders and cancels will be posted to the exchange for real.\n")
        body.append("Dry-run protection is OFF.", style=f"bold {DOWN}")
        body.append(" This choice is remembered across sessions.")

        def _confirmed(ok: bool | None) -> None:
            if ok:
                self.reconfigure(
                    self.settings.model_copy(update={"polymarket_execution_live": True})
                )
                save_execution_live(True)
                self.notify(
                    "LIVE - orders and cancels post to the exchange (L to drop back to DRY)",
                    severity="warning",
                    timeout=5,
                )

        self.push_screen(ConfirmModal("ENABLE LIVE TRADING", body, "go live"), _confirmed)

    def action_toggle_density(self) -> None:
        """Flip condensed/spacious layout; the choice persists across sessions."""
        new = "spacious" if self.density == "condensed" else "condensed"
        self.remove_class(f"density-{self.density}")
        self.density = new
        self.add_class(f"density-{new}")
        save_density(new)
        self.notify(f"{new} layout (T to switch back)", timeout=4)

    def action_portfolio(self) -> None:
        """'p': switch the drill root to the portfolio (same top level as Home)."""
        if not self.settings.can_read_portfolio:
            self.notify(
                "Portfolio needs a funder address - press A to authenticate", severity="warning"
            )
            return
        host = self._nav_host()
        if host is None:
            return
        while len(self.screen_stack) > 1:
            self.pop_screen()
        if isinstance(host.root_pane, PortfolioPane):
            host.reset_to_root()
        else:
            host.set_root(PortfolioPane(), "Portfolio")

    def open_reconciliation(self, target: ReconcileTarget) -> None:
        """Jump to Open Orders to check whether a status-unknown post landed."""
        self.reconcile_target = target
        if not self.settings.can_read_portfolio:
            self.notify(
                "Add a funder address (press A) to check Open Orders", severity="warning"
            )
            return
        host = self._nav_host()
        if host is None:
            return
        while len(self.screen_stack) > 1:
            self.pop_screen()
        if isinstance(host.root_pane, PortfolioPane):
            host.reset_to_root()
            host.root_pane.enter_reconciliation()
        else:
            # A fresh pane enters reconciliation from on_mount (reconcile_target set).
            host.set_root(PortfolioPane(), "Portfolio")

    def action_help(self) -> None:
        self._push_unless_current(HelpScreen, HelpScreen)

    def action_home(self) -> None:
        while len(self.screen_stack) > 1:
            self.pop_screen()
        base = self.screen_stack[0]
        if isinstance(base, NavHost):
            base.go_home()

    def action_nav_back(self) -> None:
        # Screens may consume "back" to step out one level (close a panel,
        # collapse an expanded view) before the screen itself pops.
        handler = getattr(self.screen, "handle_back", None)
        if handler is not None and handler():
            return
        if len(self.screen_stack) > 1:
            self.pop_screen()
