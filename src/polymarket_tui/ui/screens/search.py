"""Search screen: debounced Gamma public-search with combobox navigation.

Two result modes toggled with tab: MARKETS (event list + preview) and
TRADERS (profile list + overview). Arrows drive the active list while focus
stays in the input; enter opens the highlighted result.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import Profile
from polymarket_tui.ui.screens.portfolio import pnl_text
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.event_table import EventsTable
from polymarket_tui.ui.widgets.preview import EventsBrowser
from polymarket_tui.ui.widgets.vim_table import VimDataTable

DEBOUNCE_SECONDS = 0.35


class SearchInput(Input):
    """Up/down move the active result list's cursor without leaving the input."""

    BINDINGS = [
        Binding("down", "move_result(1)", "next result", show=False),
        Binding("up", "move_result(-1)", "prev result", show=False),
    ]

    def action_move_result(self, delta: int) -> None:
        table = self.screen.active_table()
        if table.row_count == 0:
            return
        row = table.cursor_row if table.cursor_row is not None else -1
        table.move_cursor(row=max(0, min(table.row_count - 1, row + delta)))


class SearchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back_or_pop", "back"),
        Binding("tab", "toggle_mode", "markets/traders"),
        Binding("shift+tab", "toggle_mode", "markets/traders", show=False),
        Binding("space", "toggle_watch", "star", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._timer = None
        self._mode = "markets"  # or "traders"

    def compose(self) -> ComposeResult:
        yield AppHeader("search")
        yield SearchInput(
            placeholder="search markets and traders... (tab switches mode)",
            id="search-input",
        )
        yield Static(id="mode-line", classes="subtle")
        yield EventsBrowser(id="search-browser")
        with Horizontal(id="traders-block"):
            yield VimDataTable(cursor_type="row", zebra_stripes=True, id="traders-table")
            overview = VerticalScroll(Static(id="trader-overview"), id="trader-overview-pane")
            overview.can_focus = False
            yield overview
        yield Footer()

    def on_mount(self) -> None:
        self.title = "search"
        self._profiles: list[Profile] = []
        traders = self.query_one("#traders-table", VimDataTable)
        traders.add_column("Trader", width=32, key="name")
        traders.add_column("Address", width=16, key="address")
        traders.add_column("Bio", width=50, key="bio")
        self._apply_mode()
        self.query_one(SearchInput).focus()

    # -- mode ----------------------------------------------------------------

    def active_table(self) -> VimDataTable:
        if self._mode == "traders":
            return self.query_one("#traders-table", VimDataTable)
        return self.query_one(EventsTable)

    def action_toggle_mode(self) -> None:
        self._mode = "traders" if self._mode == "markets" else "markets"
        self._apply_mode()

    def _apply_mode(self) -> None:
        markets = self._mode == "markets"
        self.query_one(EventsBrowser).display = markets
        self.query_one("#traders-block", Horizontal).display = not markets
        line = Text()
        line.append("  results: ")
        line.append("MARKETS", style="bold" if markets else "dim")
        line.append("  /  ")
        line.append("TRADERS", style="dim" if markets else "bold")
        line.append("   (tab switches)", style="dim")
        self.query_one("#mode-line", Static).update(line)
        if not markets:
            self._refresh_trader_overview()

    # -- search ---------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._timer is not None:
            self._timer.stop()
        query = event.value.strip()
        if len(query) < 2:
            return
        self._timer = self.set_timer(DEBOUNCE_SECONDS, lambda: self.run_search(query))

    @work(exclusive=True)
    async def run_search(self, query: str) -> None:
        try:
            events, profiles = await self.app.gamma.search(query)
        except Exception as exc:
            self.notify(f"Search failed: {exc}", severity="error")
            return
        events = [e for e in events if e.top_market is not None]
        table = self.query_one(EventsTable)
        table.set_events(events, set(self.app.watchlist.slugs))
        browser = self.query_one(EventsBrowser)
        browser.preview.show_event(events[0] if events else None)

        self._profiles = profiles[:10]
        traders = self.query_one("#traders-table", VimDataTable)
        traders.clear()
        for prof in self._profiles:
            star = "*" if self.app.watchlist.is_watched_user(prof.proxy_wallet) else " "
            traders.add_row(
                star + " " + fmt.trunc(prof.display_name, 29),
                f"{prof.proxy_wallet[:6]}...{prof.proxy_wallet[-4:]}",
                fmt.trunc(prof.bio or "", 50),
                key=prof.proxy_wallet,
            )
        if self._mode == "traders":
            self._refresh_trader_overview()

    # -- open / preview ------------------------------------------------------------

    def _highlighted_profile(self) -> Profile | None:
        traders = self.query_one("#traders-table", VimDataTable)
        if traders.cursor_row is None or traders.row_count == 0:
            return None
        address = str(traders.coordinate_to_cell_key((traders.cursor_row, 0)).row_key.value)
        return next((p for p in self._profiles if p.proxy_wallet == address), None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._mode == "traders":
            self._open_trader()
            return
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id == "traders-table":
            self._open_trader()
            return
        selected = self.query_one(EventsTable).highlighted_event()
        if selected is not None:
            self.app.open_event(selected)

    def _open_trader(self) -> None:
        profile = self._highlighted_profile()
        if profile is not None:
            from polymarket_tui.ui.screens.user import UserScreen

            self.app.push_screen(UserScreen(profile.proxy_wallet, profile.display_name))

    def on_data_table_row_highlighted(self, event) -> None:
        if event.data_table.id == "traders-table":
            self._refresh_trader_overview()

    def _refresh_trader_overview(self) -> None:
        profile = self._highlighted_profile()
        if profile is not None:
            self.load_trader_overview(profile)

    @work(exclusive=True, group="trader-overview")
    async def load_trader_overview(self, profile: Profile) -> None:
        """Hovered/highlighted trader: value + top positions in the side pane."""
        pane = self.query_one("#trader-overview", Static)
        out = Text()
        out.append(profile.display_name + "\n", style="bold")
        out.append(f"{profile.proxy_wallet[:8]}...{profile.proxy_wallet[-6:]}\n", style="dim")
        if profile.bio:
            out.append(fmt.trunc(profile.bio, 120) + "\n", style="dim")
        pane.update(out)
        try:
            value = await self.app.data.portfolio_value(profile.proxy_wallet)
            positions = await self.app.data.positions(profile.proxy_wallet, limit=50)
        except Exception:
            out.append("\n(positions unavailable)", style="dim")
            pane.update(out)
            return
        out.append("\npositions ", style="dim")
        out.append(f"${value or 0:,.2f}\n\n", style="bold")
        top = sorted(
            (p for p in positions if p.size >= 0.01),
            key=lambda p: p.current_value,
            reverse=True,
        )
        for pos in top[:8]:
            out.append(f"{fmt.trunc(pos.title, 24):<25}", style="")
            out.append(f"{fmt.money(pos.current_value):>8} ")
            out.append_text(pnl_text(pos.cash_pnl, pos.percent_pnl))
            out.append("\n")
        if not top:
            out.append("no open positions\n", style="dim")
        pane.update(out)

    # -- star ----------------------------------------------------------------------

    def action_toggle_watch(self) -> None:
        if self._mode == "traders":
            profile = self._highlighted_profile()
            if profile is None:
                return
            watched = self.app.watchlist.toggle_user(profile.proxy_wallet, profile.display_name)
            self.query_one("#traders-table", VimDataTable).update_cell(
                profile.proxy_wallet,
                "name",
                ("*" if watched else " ") + " " + fmt.trunc(profile.display_name, 29),
            )
            return
        table = self.query_one(EventsTable)
        if not table.has_focus:
            return
        selected = table.highlighted_event()
        if selected is None:
            return
        watched = self.app.watchlist.toggle(selected.slug)
        table.set_star(selected.slug, watched)

    def on_vim_data_table_top_reached(self, message) -> None:
        self.query_one(SearchInput).focus()

    def action_back_or_pop(self) -> None:
        self.app.pop_screen()
