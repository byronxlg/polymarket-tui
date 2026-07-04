"""Portfolio: positions with live P&L, open orders, activity history."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static, TabbedContent, TabPane

from polymarket_tui.core import fmt
from polymarket_tui.models.market import PricePoint
from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.confirm_modal import ConfirmModal
from polymarket_tui.ui.widgets.linechart import render_chart
from polymarket_tui.ui.widgets.tables import position_row, setup_positions_columns
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class OrdersTable(VimDataTable):
    """Open-orders table: the cancel binding lives here so the footer only
    advertises it while this table is focused."""

    BINDINGS = [Binding("x", "screen.cancel_order", "cancel order")]


class PortfolioScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "prev_pane", "prev tab", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader("portfolio")
        yield Static("loading balances...", id="balance-line", classes="screen-title")
        with TabbedContent(id="portfolio-tabs"):
            with TabPane("Positions", id="pane-positions"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="positions-table")
            with TabPane("Open orders", id="pane-orders"):
                yield OrdersTable(cursor_type="row", zebra_stripes=True, id="orders-table")
            with TabPane("History", id="pane-history"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="history-table")
        with Vertical(id="pnl-pane"):
            yield Static(id="pnl-title")
            yield Static(id="pnl-chart")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "portfolio"
        self._orders: list[OpenOrder] = []

        positions = self.query_one("#positions-table", VimDataTable)
        setup_positions_columns(positions, flag_column=True)

        orders = self.query_one("#orders-table", OrdersTable)
        orders.add_column("Market", width=44, key="market")
        orders.add_column("Side", width=5, key="side")
        orders.add_column("Outcome", width=10, key="outcome")
        orders.add_column("Price", width=7, key="price")
        orders.add_column("Size", width=8, key="size")
        orders.add_column("Filled", width=8, key="filled")
        orders.add_column("Placed", width=12, key="placed")

        history = self.query_one("#history-table", VimDataTable)
        history.add_column("When", width=13, key="when")
        history.add_column("Type", width=8, key="type")
        history.add_column("Side", width=5, key="side")
        history.add_column("Market", width=42, key="market")
        history.add_column("Outcome", width=10, key="outcome")
        history.add_column("Price", width=7, key="price")
        history.add_column("Size", width=8, key="size")
        history.add_column("USDC", width=10, key="usdc")

        # Tab strip inside TabbedContent should not trap focus/arrow keys.
        for tabs in self.query("Tabs"):
            tabs.can_focus = False
        positions.focus()
        self.load_all()

    # -- loaders -------------------------------------------------------------

    def action_refresh(self) -> None:
        self.app.portfolio.invalidate()
        self.load_all()

    def load_all(self) -> None:
        self.load_balances()
        self.load_positions()
        self.load_orders()
        self.load_history()
        self.load_pnl()

    def on_resize(self) -> None:
        self._draw_pnl()

    @work(exclusive=True, group="pnl")
    async def load_pnl(self) -> None:
        try:
            self._pnl = await self.app.data.user_pnl(self.app.portfolio.user)
        except Exception:
            self._pnl = []
        title = self.query_one("#pnl-title", Static)
        if len(self._pnl) >= 2:
            latest, first = self._pnl[-1].p, self._pnl[0].p
            delta = latest - first
            style = "green" if delta >= 0 else "red"
            text = Text()
            text.append("PROFIT 30d  ", style="bold")
            text.append(f"${latest:,.2f} all-time", style="bold")
            text.append(f"  {delta:+,.2f} this window", style=style)
            title.update(text)
        else:
            title.update(Text("PROFIT 30d  (no history)", style="dim"))
        self._draw_pnl()

    def _draw_pnl(self) -> None:
        chart = self.query_one("#pnl-chart", Static)
        points = getattr(self, "_pnl", [])
        if len(points) < 2:
            chart.update(Text(""))
            return
        size = chart.size
        if size.width < 12 or size.height < 4:
            return
        # render_chart plots p*100, so feed dollars/100 to label the axis in dollars.
        scaled = [PricePoint(t=pt.t, p=pt.p / 100) for pt in points]
        color = (46, 204, 113) if points[-1].p >= points[0].p else (231, 76, 60)
        chart.update(
            render_chart(
                [(scaled, color)],
                width=size.width,
                height=size.height + 1,  # no separate axis row budgeted; keep compact
                time_format="%b %d",
                clamp=None,
            )
        )

    @work(exclusive=True, group="balances")
    async def load_balances(self) -> None:
        app = self.app
        parts = [f"mode {app.settings.mode.value}"]
        try:
            value = await app.portfolio.portfolio_value()
            if value is not None:
                parts.insert(0, f"positions {fmt.money(value)}")
            balance = await app.portfolio.usdc_balance()
            if balance is not None:
                parts.insert(0, f"cash {fmt.money(balance)}")
                if value is not None:
                    parts.insert(0, f"total {fmt.money(balance + value)}")
        except Exception as exc:
            parts.append(f"balance error: {exc}")
        self.query_one("#balance-line", Static).update("  |  ".join(parts))

    @work(exclusive=True, group="positions")
    async def load_positions(self) -> None:
        table = self.query_one("#positions-table", VimDataTable)
        try:
            positions = await self.app.portfolio.positions(force=True)
        except Exception as exc:
            self.notify(f"positions unavailable: {exc}", severity="error")
            return
        table.clear()
        for pos in sorted(positions, key=lambda p: p.current_value, reverse=True):
            if pos.size < 0.01:
                continue
            table.add_row(
                *position_row(pos),
                self._resolution_flag(pos),
                key=f"{pos.slug}|{pos.asset}",
            )

    @staticmethod
    def _resolution_flag(pos) -> Text | str:
        """Resolved markets: won shares redeem for USD1 each (on the website -
        redemption is an on-chain transaction this client does not send)."""
        if not pos.redeemable:
            return ""
        if pos.cur_price >= 0.5:
            return Text("won - redeem on web", style="yellow")
        return Text("resolved - lost", style="dim red")

    @work(exclusive=True, group="orders")
    async def load_orders(self) -> None:
        table = self.query_one("#orders-table", VimDataTable)
        try:
            self._orders = await self.app.portfolio.open_orders()
        except Exception as exc:
            self.notify(f"open orders unavailable: {exc}", severity="warning")
            return
        table.clear()
        titles = await self._order_titles(self._orders)
        for order in self._orders:
            table.add_row(
                fmt.trunc(titles.get(order.market, order.market[:20] + "…"), 44),
                Text(order.side, style="green" if order.side == "BUY" else "red"),
                order.outcome or "-",
                fmt.cents(order.price),
                f"{order.original_size:,.0f}",
                f"{order.size_matched:,.0f}",
                order.when.astimezone().strftime("%b %d %H:%M") if order.when else "-",
                key=order.id,
            )

    async def _order_titles(self, orders: list[OpenOrder]) -> dict[str, str]:
        """Resolve condition ids to market questions via positions, then Gamma."""
        titles: dict[str, str] = {}
        try:
            for pos in await self.app.portfolio.positions():
                titles[pos.condition_id] = pos.title
        except Exception:
            pass
        missing = {o.market for o in orders if o.market and o.market not in titles}
        for cid in missing:
            try:
                market = await self.app.gamma.market_by_condition(cid)
                if market is not None:
                    titles[cid] = market.question
            except Exception:
                continue
        return titles

    @work(exclusive=True, group="history")
    async def load_history(self) -> None:
        table = self.query_one("#history-table", VimDataTable)
        try:
            items = await self.app.portfolio.activity()
        except Exception as exc:
            self.notify(f"history unavailable: {exc}", severity="warning")
            return
        table.clear()
        for i, item in enumerate(items):
            table.add_row(
                item.when.astimezone().strftime("%b %d %H:%M"),
                item.type,
                Text(item.side, style="green" if item.side == "BUY" else "red")
                if item.side
                else "-",
                fmt.trunc(item.title, 42),
                fmt.trunc(item.outcome, 10),
                fmt.cents(item.price) if item.type == "TRADE" else "-",
                f"{item.size:,.0f}" if item.size else "-",
                fmt.money(item.usdc_size),
                key=f"{i}|{item.slug}",
            )

    # -- actions ---------------------------------------------------------------

    def _active_pane(self) -> str:
        return self.query_one(TabbedContent).active

    def action_next_pane(self) -> None:
        tabbed = self.query_one(TabbedContent)
        panes = ["pane-positions", "pane-orders", "pane-history"]
        idx = (panes.index(tabbed.active) + 1) % len(panes) if tabbed.active in panes else 0
        tabbed.active = panes[idx]

    def action_prev_pane(self) -> None:
        tabbed = self.query_one(TabbedContent)
        panes = ["pane-positions", "pane-orders", "pane-history"]
        idx = (panes.index(tabbed.active) - 1) % len(panes) if tabbed.active in panes else 0
        tabbed.active = panes[idx]

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane = event.pane.id or ""
        table_id = {
            "pane-positions": "#positions-table",
            "pane-orders": "#orders-table",
            "pane-history": "#history-table",
        }.get(pane)
        if table_id:
            self.query_one(table_id, VimDataTable).focus()
        self.refresh_bindings()

    def on_data_table_row_selected(self, event) -> None:
        if self._active_pane() != "pane-positions":
            return
        slug, _, asset = str(event.row_key.value).partition("|")
        self.open_position_market(slug, asset)

    @work(exclusive=True, group="open-market")
    async def open_position_market(self, slug: str, asset: str) -> None:
        condition_id = ""
        try:
            for pos in await self.app.portfolio.positions():
                if pos.asset == asset:
                    condition_id = pos.condition_id
                    break
        except Exception:
            pass
        market = None
        try:
            market = await self.app.gamma.market_by_slug(slug)
            if market is None and condition_id:
                # Resolved positions often drop out of the slug lookup.
                market = await self.app.gamma.market_by_condition(condition_id)
        except Exception as exc:
            self.notify(f"could not open market: {exc}", severity="error")
            return
        if market is None:
            self.notify("Market is no longer listed (resolved)", severity="warning")
            return
        self.app.open_market(market)

    def action_cancel_order(self) -> None:
        if self._active_pane() != "pane-orders":
            return
        table = self.query_one("#orders-table", VimDataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        order = next((o for o in self._orders if o.id == str(row_key.value)), None)
        if order is None:
            return
        body = Text()
        body.append(f"{order.side} {order.remaining:,.0f} @ {fmt.cents(order.price)}\n")
        body.append(f"order {order.id[:18]}…", style="dim")

        def _done(confirmed: bool | None) -> None:
            if confirmed:
                self.cancel_order_worker(order.id)

        self.app.push_screen(ConfirmModal("CANCEL ORDER", body, "cancel order"), _done)

    @work(exclusive=True, group="cancel")
    async def cancel_order_worker(self, order_id: str) -> None:
        result = await self.app.orders.cancel(order_id)
        if result.ok and result.dry_run:
            self.notify("DRY RUN: cancel not posted (set POLYMARKET_EXECUTION_LIVE=1)", timeout=6)
        elif result.ok:
            self.notify("Order cancelled")
        else:
            self.notify(f"Cancel failed: {result.error}", severity="error", timeout=8)
        self.load_orders()
