"""Public trader profile: positions and recent activity for any address."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static, TabbedContent, TabPane

from polymarket_tui.core import fmt
from polymarket_tui.ui.screens.portfolio import pnl_text
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class UserScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("space", "toggle_watch", "watch user"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "next_pane", "prev pane", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, address: str, name: str) -> None:
        super().__init__()
        self._address = address
        self._name = name

    def compose(self) -> ComposeResult:
        yield AppHeader("trader")
        yield Static(self._title_line(), classes="screen-title", id="user-title")
        with TabbedContent(id="user-tabs"):
            with TabPane("Positions", id="pane-user-positions"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="user-positions")
            with TabPane("Activity", id="pane-user-activity"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="user-activity")
        yield Footer()

    def _title_line(self) -> str:
        watched = " | watched" if self.app.watchlist.is_watched_user(self._address) else ""
        return f"{self._name}  |  {self._address[:6]}...{self._address[-4:]}{watched}"

    def on_mount(self) -> None:
        self.title = "trader"
        positions = self.query_one("#user-positions", VimDataTable)
        positions.add_column("Market", width=46, key="market")
        positions.add_column("Outcome", width=12, key="outcome")
        positions.add_column("Size", width=10, key="size")
        positions.add_column("Avg", width=7, key="avg")
        positions.add_column("Cur", width=7, key="cur")
        positions.add_column("Value", width=10, key="value")
        positions.add_column("P&L", width=16, key="pnl")

        activity = self.query_one("#user-activity", VimDataTable)
        activity.add_column("When", width=13, key="when")
        activity.add_column("Type", width=8, key="type")
        activity.add_column("Side", width=5, key="side")
        activity.add_column("Market", width=46, key="market")
        activity.add_column("Outcome", width=10, key="outcome")
        activity.add_column("Price", width=7, key="price")
        activity.add_column("Size", width=10, key="size")
        activity.add_column("USDC", width=10, key="usdc")

        for tabs in self.query("Tabs"):
            tabs.can_focus = False
        positions.focus()
        self.load_user()

    @work(exclusive=True)
    async def load_user(self) -> None:
        app = self.app
        try:
            value = await app.data.portfolio_value(self._address)
            if value is not None:
                title = self.query_one("#user-title", Static)
                title.update(self._title_line() + f"  |  positions {fmt.money(value)}")
        except Exception:
            pass

        positions_table = self.query_one("#user-positions", VimDataTable)
        try:
            positions = await app.data.positions(self._address)
        except Exception as exc:
            self.notify(f"positions unavailable: {exc}", severity="error")
            positions = []
        positions_table.clear()
        for pos in sorted(positions, key=lambda p: p.current_value, reverse=True):
            if pos.size < 0.01:
                continue
            positions_table.add_row(
                fmt.trunc(pos.title, 46),
                fmt.trunc(pos.outcome, 12),
                fmt.compact_size(pos.size),
                fmt.cents(pos.avg_price),
                fmt.cents(pos.cur_price),
                fmt.money(pos.current_value),
                pnl_text(pos.cash_pnl, pos.percent_pnl),
                key=f"{pos.slug}|{pos.asset}",
            )

        activity_table = self.query_one("#user-activity", VimDataTable)
        try:
            items = await app.data.activity(self._address, limit=60)
        except Exception:
            items = []
        activity_table.clear()
        for i, item in enumerate(items):
            activity_table.add_row(
                item.when.astimezone().strftime("%b %d %H:%M"),
                item.type,
                Text(item.side, style="green" if item.side == "BUY" else "red")
                if item.side
                else "-",
                fmt.trunc(item.title, 46),
                fmt.trunc(item.outcome, 10),
                fmt.cents(item.price) if item.type == "TRADE" else "-",
                fmt.compact_size(item.size) if item.size else "-",
                fmt.money(item.usdc_size),
                key=f"{i}|{item.slug}",
            )

    def on_data_table_row_selected(self, event) -> None:
        key = str(event.row_key.value)
        if self.query_one(TabbedContent).active == "pane-user-activity":
            slug = key.split("|", 1)[1] if "|" in key else ""  # keys are "index|slug"
        else:
            slug = key.split("|", 1)[0]  # keys are "slug|asset"
        self.open_market_by_slug(slug)

    @work(exclusive=True, group="open-market")
    async def open_market_by_slug(self, slug: str) -> None:
        if not slug:
            return
        try:
            market = await self.app.gamma.market_by_slug(slug)
        except Exception:
            return
        if market is not None:
            self.app.open_market(market)

    def action_toggle_watch(self) -> None:
        watched = self.app.watchlist.toggle_user(self._address, self._name)
        self.notify(f"{'Watching' if watched else 'Unwatched'} {self._name}", timeout=3)
        self.query_one("#user-title", Static).update(self._title_line())
        self.load_user()

    def action_next_pane(self) -> None:
        tabbed = self.query_one(TabbedContent)
        panes = ["pane-user-positions", "pane-user-activity"]
        idx = (panes.index(tabbed.active) + 1) % len(panes) if tabbed.active in panes else 0
        tabbed.active = panes[idx]
        table_id = "#user-positions" if idx == 0 else "#user-activity"
        self.query_one(table_id, VimDataTable).focus()

    def action_refresh(self) -> None:
        self.load_user()
