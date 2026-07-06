"""Portfolio: positions with live P&L, open orders, activity history.

A NavHost root pane (like Home and Watched, Byron's request 2026-07-05):
'p' switches the drill root here, so opening a market from a position keeps
the portfolio as the 30% parent and left/esc steps back into it.
"""

from __future__ import annotations

import time
from decimal import Decimal

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane

from polymarket_tui.core import fmt
from polymarket_tui.core.links import copy_to_clipboard, market_url, open_in_browser
from polymarket_tui.models.portfolio import OpenOrder, Position
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.theme import AMBER, BLUE, DOWN, UP
from polymarket_tui.ui.tiers import ColumnSpec, Tier, TierAware, effective_tier, fit_columns
from polymarket_tui.ui.widgets.order_details import cancel_confirm_text
from polymarket_tui.ui.widgets.pnl_strip import PnlStrip
from polymarket_tui.ui.widgets.tables import (
    ACTIVITY_TIER_COLUMNS,
    POSITIONS_SPACIOUS_TIER_COLUMNS,
    POSITIONS_TIER_COLUMNS,
    activity_row,
    position_row,
    setup_activity_columns,
    setup_positions_columns,
)
from polymarket_tui.ui.widgets.vim_table import VimDataTable

ORDERS_TIER_COLUMNS: dict[Tier, tuple[tuple[str, str, int], ...]] = {
    "full": (
        ("market", "Market", 44),
        ("side", "Side", 5),
        ("outcome", "Outcome", 10),
        ("price", "Price", 7),
        ("size", "Size", 8),
        ("filled", "Filled", 8),
        ("placed", "Placed", 12),
    ),
    "medium": (
        ("market", "Market", 36),
        ("side", "Side", 5),
        ("outcome", "Outcome", 10),
        ("price", "Price", 7),
        ("size", "Size", 8),
    ),
    "compact": (
        ("market", "Market", 24),
        ("side", "Side", 5),
        ("price", "Price", 7),
    ),
}


def _pane_of(widget) -> PortfolioPane | None:
    return next((a for a in widget.ancestors if isinstance(a, PortfolioPane)), None)


class OrdersTable(VimDataTable):
    """Open-orders table: the cancel binding lives here so the footer only
    advertises it while this table is focused."""

    BINDINGS = [
        Binding("x", "cancel_order", "cancel order"),
        # enter confirms an armed cancel; otherwise the row just selects.
        Binding("enter", "confirm_or_select", "confirm", show=False),
    ]

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """No open orders - nothing to cancel; don't advertise x."""
        if action == "cancel_order" and self.row_count == 0:
            return False
        return super().check_action(action, parameters)

    def action_cancel_order(self) -> None:
        pane = _pane_of(self)
        if pane is not None:
            pane.action_cancel_order()

    def action_confirm_or_select(self) -> None:
        pane = _pane_of(self)
        if pane is not None and pane.confirm_pending_cancel():
            return
        self.action_select_cursor()


class PositionsTable(VimDataTable):
    """Positions table: the open-on-web binding lives here so the footer only
    advertises it while this table is focused (won positions redeem on the web)."""

    BINDINGS = [
        Binding("s", "sell_position", "sell"),
        Binding("o", "open_on_web", "open on web"),
    ]

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Empty positions list - nothing to sell or open on the web."""
        if action in ("open_on_web", "sell_position") and self.row_count == 0:
            return False
        return super().check_action(action, parameters)

    def action_open_on_web(self) -> None:
        pane = _pane_of(self)
        if pane is not None:
            pane.action_open_on_web()

    def action_sell_position(self) -> None:
        pane = _pane_of(self)
        if pane is not None:
            pane.action_sell_position()


class PortfolioPane(TierAware, Vertical):
    header_title = "portfolio"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "prev_pane", "prev tab", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._orders: list[OpenOrder] = []
        self._positions: list[Position] = []
        self._history_items: list = []
        self._order_titles_cache: dict[str, str] = {}
        self._pending_cancel: OpenOrder | None = None
        self._cancel_armed_at = 0.0
        self._pos_spec: list[ColumnSpec] = list(POSITIONS_TIER_COLUMNS["full"])
        self._pos_tier: Tier = "full"
        self._rendered_density: str = "condensed"
        self._ord_spec: list[ColumnSpec] = list(ORDERS_TIER_COLUMNS["full"])
        self._act_spec: list[ColumnSpec] = list(ACTIVITY_TIER_COLUMNS["full"])

    def compose(self) -> ComposeResult:
        yield Static("loading balances...", id="balance-line", classes="screen-title")
        yield Static(id="reconcile-banner")
        yield Static(id="cancel-strip")
        with TabbedContent(id="portfolio-tabs"):
            with TabPane("Positions", id="pane-positions"):
                yield PositionsTable(cursor_type="row", zebra_stripes=True, id="positions-table")
                yield Static(id="lost-note")
            with TabPane("Open orders", id="pane-orders"):
                yield OrdersTable(cursor_type="row", zebra_stripes=True, id="orders-table")
            with TabPane("History", id="pane-history"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="history-table")
        yield PnlStrip(id="pnl-pane")

    def focus_inner(self) -> None:
        table_id = {
            "pane-positions": "#positions-table",
            "pane-orders": "#orders-table",
            "pane-history": "#history-table",
        }.get(self._active_pane())
        if table_id:
            self.query_one(table_id, VimDataTable).focus()

    def handle_back(self) -> bool:
        """left/esc clears an armed cancel strip before leaving the pane."""
        if self._pending_cancel is not None:
            self._clear_pending_cancel()
            return True
        return False

    def _pos_columns(self) -> dict[Tier, tuple]:
        """Positions column sets for the current density (spacious re-composes rows)."""
        if self.app.density == "spacious":
            return POSITIONS_SPACIOUS_TIER_COLUMNS
        return POSITIONS_TIER_COLUMNS

    def on_mount(self) -> None:
        self.query_one("#cancel-strip", Static).display = False
        self.query_one("#lost-note", Static).display = False
        self._rendered_density = self.app.density
        self._pos_spec = list(self._pos_columns()[self.tier])
        self._pos_tier = self.tier
        self._ord_spec = list(ORDERS_TIER_COLUMNS[self.tier])
        self._act_spec = list(ACTIVITY_TIER_COLUMNS[self.tier])
        self._build_columns()
        # Tab strip inside TabbedContent should not trap focus/arrow keys.
        for tabs in self.query("Tabs"):
            tabs.can_focus = False
        self.query_one("#positions-table", PositionsTable).focus()
        self.load_all()
        self.tier_ready()
        self._schedule_refit()
        if self.app.reconcile_target is not None:
            self.enter_reconciliation()

    def on_unmount(self) -> None:
        # Reconciliation is resolved once the user has looked; don't persist it.
        self.app.reconcile_target = None

    # -- width tiers -----------------------------------------------------------

    def _build_columns(self) -> None:
        positions = self.query_one("#positions-table", PositionsTable)
        positions.clear(columns=True)
        setup_positions_columns(
            positions, flag_column=self._pos_tier == "full", columns=self._pos_spec
        )
        orders = self.query_one("#orders-table", OrdersTable)
        orders.clear(columns=True)
        for key, label, width in self._ord_spec:
            orders.add_column(label, width=width, key=key)
        history = self.query_one("#history-table", VimDataTable)
        history.clear(columns=True)
        setup_activity_columns(history, columns=self._act_spec)

    def on_tier_changed(self, tier: Tier) -> None:
        self._schedule_refit()

    def on_density_changed(self, density: str) -> None:
        """T toggled: positions re-compose into two-line rows (app calls this)."""
        self._schedule_refit()

    def on_resize(self) -> None:
        if self._tier_ready:
            self._schedule_refit()

    def _schedule_refit(self) -> None:
        # The tables live in tabs (the hidden ones measure 0 wide), so fit
        # all three against the pane's own width after layout settles.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        if not alive(self):
            return  # call_after_refresh can fire after the pane is torn down
        width = self.size.width - 2  # border + slack
        if width <= 0:
            return
        pos_columns = self._pos_columns()
        pos_tier = effective_tier(self.tier, width, pos_columns)
        ord_tier = effective_tier(self.tier, width, ORDERS_TIER_COLUMNS)
        act_tier = effective_tier(self.tier, width, ACTIVITY_TIER_COLUMNS)
        pos_flex = max((len(p.title) for p in self._positions), default=0) or None
        pos_spec = fit_columns(pos_columns[pos_tier], width, "market", pos_flex)
        ord_spec = fit_columns(ORDERS_TIER_COLUMNS[ord_tier], width, "market")
        act_spec = fit_columns(ACTIVITY_TIER_COLUMNS[act_tier], width, "market")
        if (pos_spec, ord_spec, act_spec) == (
            self._pos_spec,
            self._ord_spec,
            self._act_spec,
        ) and self._rendered_density == self.app.density:
            return
        self._pos_spec, self._ord_spec, self._act_spec = pos_spec, ord_spec, act_spec
        self._pos_tier = pos_tier
        self._rendered_density = self.app.density
        self._build_columns()
        self._render_positions()
        self._render_orders()
        self._render_history()

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

    def load_pnl(self) -> None:
        self.query_one("#pnl-pane", PnlStrip).show_user(self.app.portfolio.user)

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
        if not alive(self):
            return  # pane torn down while we fetched
        self.query_one("#balance-line", Static).update("  |  ".join(parts))

    @work(exclusive=True, group="positions")
    async def load_positions(self) -> None:
        try:
            positions = await self.app.portfolio.positions(force=True)
        except Exception as exc:
            self.notify(f"positions unavailable: {exc}", severity="error")
            return
        if not alive(self):
            return  # pane torn down while we fetched
        self._positions = positions
        self._render_positions()

    def _render_positions(self) -> None:
        table = self.query_one("#positions-table", VimDataTable)
        table.clear()
        full = self._pos_tier == "full"
        density = self.app.density
        height = 2 if density == "spacious" else 1
        lost = 0
        for pos in sorted(self._positions, key=lambda p: p.current_value, reverse=True):
            if pos.size < 0.01:
                continue
            if pos.resolved_loss:
                lost += 1
                continue
            row = position_row(pos, columns=self._pos_spec, density=density)
            if full:
                row.append(self._resolution_flag(pos))
            table.add_row(*row, key=f"{pos.slug}|{pos.asset}", height=height)
        table.refresh_bindings()  # the open-on-web hint gates on row_count
        note = self.query_one("#lost-note", Static)
        # Compact tier is context-only (primary list survives); inline display
        # flags override stylesheet rules, so the tier gate lives here too.
        note.display = lost > 0 and self._pos_tier != "compact"
        if lost:
            word = "losses" if lost != 1 else "loss"
            note.update(
                Text(
                    f"{lost} resolved {word} hidden - worth 0, nothing to claim",
                    style="dim",
                )
            )

    @staticmethod
    def _resolution_flag(pos) -> Text | str:
        """Resolved markets: won shares redeem for USD1 each (on the website -
        redemption is an on-chain transaction this client does not send).
        Losses never reach the table (_render_positions drops resolved_loss)."""
        if not pos.redeemable:
            return ""
        return Text("won - redeem on web", style=AMBER)

    @work(exclusive=True, group="orders")
    async def load_orders(self) -> None:
        try:
            self._orders = await self.app.portfolio.open_orders(force=True)
        except Exception as exc:
            if not alive(self):
                return  # pane torn down while we fetched
            self.notify(f"open orders unavailable: {exc}", severity="warning")
            # On the reconciliation path the user is waiting on a verdict; a stuck
            # "Checking..." banner is worse than an honest "could not check".
            if self.app.reconcile_target is not None:
                banner = self.query_one("#reconcile-banner", Static)
                banner.add_class("active")
                banner.update(
                    Text(
                        f"COULD NOT CHECK - open orders unavailable ({exc}). Retry with r; "
                        f"do not re-place {self.app.reconcile_target.summary} until confirmed.",
                        style=f"bold {AMBER}",
                    )
                )
            return
        self._order_titles_cache = await self._order_titles(self._orders)
        if not alive(self):
            return  # pane torn down while we fetched
        self._render_orders()
        self._update_reconcile_banner()

    def _render_orders(self) -> None:
        table = self.query_one("#orders-table", VimDataTable)
        table.clear()
        titles = self._order_titles_cache
        target = self.app.reconcile_target
        widths = {key: width for key, _, width in self._ord_spec}
        for order in self._orders:
            match = target is not None and target.matches(order)
            title = fmt.trunc(
                titles.get(order.market, order.market[:20] + "…"), widths["market"]
            )
            cells = {
                "market": Text("► " + title, style=f"bold {BLUE}") if match else title,
                "side": Text(order.side, style=UP if order.side == "BUY" else DOWN),
                "outcome": order.outcome or "-",
                "price": fmt.cents(order.price),
                "size": f"{order.original_size:,.0f}",
                "filled": f"{order.size_matched:,.0f}",
                "placed": order.when.astimezone().strftime("%b %d %H:%M") if order.when else "-",
            }
            table.add_row(*(cells[key] for key, _, _ in self._ord_spec), key=order.id)
        table.refresh_bindings()  # the x-cancel hint gates on row_count

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

    # -- reconciliation (issue #3) -------------------------------------------

    def enter_reconciliation(self) -> None:
        """Focus Open Orders for a status-unknown post and re-fetch to check it."""
        if self.app.reconcile_target is None:
            return
        self.query_one(TabbedContent).active = "pane-orders"
        banner = self.query_one("#reconcile-banner", Static)
        banner.add_class("active")
        banner.update(
            Text(
                f"Checking Open Orders for: {self.app.reconcile_target.summary} ...",
                style="dim",
            )
        )
        self.query_one("#orders-table", OrdersTable).focus()
        self.load_orders()

    def _update_reconcile_banner(self) -> None:
        target = self.app.reconcile_target
        banner = self.query_one("#reconcile-banner", Static)
        if target is None:
            banner.remove_class("active")
            return
        banner.add_class("active")
        matches = [o for o in self._orders if target.matches(o)]
        if matches:
            resting = sum(o.remaining for o in matches)
            banner.update(
                Text(
                    f"LANDED - order is resting ({resting:,.0f} shares). {target.summary}. "
                    "Do NOT re-place; cancel with x if unintended.",
                    style=f"bold {UP}",
                )
            )
        else:
            banner.update(
                Text(
                    f"NOT FOUND - no resting order matches {target.summary}. The post did not "
                    "land; it is safe to re-place. (A very recent fill can also explain this.)",
                    style=f"bold {AMBER}",
                )
            )

    @work(exclusive=True, group="history")
    async def load_history(self) -> None:
        try:
            items = await self.app.portfolio.activity()
        except Exception as exc:
            self.notify(f"history unavailable: {exc}", severity="warning")
            return
        if not alive(self):
            return  # pane torn down while we fetched
        self._history_items = items
        self._render_history()

    def _render_history(self) -> None:
        table = self.query_one("#history-table", VimDataTable)
        table.clear()
        for i, item in enumerate(self._history_items):
            table.add_row(
                *activity_row(item, compact_size=False, columns=self._act_spec),
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
    async def open_position_market(
        self, slug: str, asset: str, sell: Position | None = None
    ) -> None:
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
        if sell is not None:
            # Cashout: open onto the held outcome with the sell form armed.
            tokens = list(market.clob_token_ids)
            index = tokens.index(sell.asset) if sell.asset in tokens else sell.outcome_index
            self.app.open_market(
                market,
                order_side="SELL",
                order_size=Decimal(str(sell.size)),
                outcome_index=index,
            )
            return
        self.app.open_market(market)

    def action_open_on_web(self) -> None:
        """Open the selected position's polymarket.com page (redeem won positions
        there; resolved markets that drop out of the in-app lookup still open)."""
        if self._active_pane() != "pane-positions":
            return
        table = self.query_one("#positions-table", PositionsTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        slug, _, asset = str(row_key.value).partition("|")
        pos = next((p for p in self._positions if p.asset == asset), None)
        url = market_url(pos.event_slug if pos else "", slug)
        if not url:
            self.notify("No web URL for this position", severity="warning")
            return
        opened = open_in_browser(url)
        copied = copy_to_clipboard(url)
        note = "Opened" if opened else "Copied" if copied else "URL"
        suffix = "  (copied)" if copied and opened else ""
        self.notify(f"{note} {url}{suffix}", timeout=6)

    def action_sell_position(self) -> None:
        """s: cash out - open the market with the sell form prefilled to the
        full position at the bid; review + a deliberate enter still confirm."""
        if self._active_pane() != "pane-positions":
            return
        table = self.query_one("#positions-table", PositionsTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        slug, _, asset = str(row_key.value).partition("|")
        pos = next((p for p in self._positions if p.asset == asset), None)
        if pos is None:
            return
        if pos.redeemable:
            # A resolved market takes no orders - cashing out means redeeming.
            self.notify("Won - redeem on polymarket.com (o opens it)", timeout=4)
            return
        if not self.app.settings.can_auth:
            self.notify(
                "Trading needs a private key + funder - press A to authenticate",
                severity="warning",
            )
            return
        self.open_position_market(slug, asset, sell=pos)

    def action_cancel_order(self) -> None:
        """x arms an inline confirm strip (no modal); enter within it cancels.
        The arming delay mirrors ConfirmModal: queued keys can't confirm."""
        if self._active_pane() != "pane-orders":
            return
        table = self.query_one("#orders-table", VimDataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
        order = next((o for o in self._orders if o.id == str(row_key.value)), None)
        if order is None:
            return
        self._pending_cancel = order
        self._cancel_armed_at = time.monotonic() + 0.35
        strip = self.query_one("#cancel-strip", Static)
        strip.update(cancel_confirm_text([order], self._order_titles_cache.get(order.market)))
        strip.display = True

    def _clear_pending_cancel(self) -> None:
        if self._pending_cancel is not None:
            self._pending_cancel = None
            self.query_one("#cancel-strip", Static).display = False

    def confirm_pending_cancel(self) -> bool:
        """enter on the orders table fires an armed cancel. True = consumed."""
        order = self._pending_cancel
        if order is None:
            return False
        if time.monotonic() < self._cancel_armed_at:
            return True  # armed but still in the queued-key window - swallow
        self._clear_pending_cancel()
        self._start_cancel(order.id)
        return True

    def on_data_table_row_highlighted(self, event) -> None:
        # Moving the cursor retargets the row - a stale confirm must not linger.
        self._clear_pending_cancel()

    def _start_cancel(self, order_id: str) -> None:
        # App-lifetime worker: navigating off the pane must not drop an in-flight
        # cancel's result (mirrors the placement path in order_panel).
        app = self.app
        pane = self

        async def _cancel_and_report() -> None:
            result = await app.orders.cancel(order_id)
            if result.ok and result.dry_run:
                app.notify(
                    "DRY RUN: cancel not posted (set POLYMARKET_EXECUTION_LIVE=1)", timeout=6
                )
            elif result.ok:
                app.notify("Order cancelled")
            else:
                app.notify(f"Cancel failed: {result.error}", severity="error", timeout=8)
            if pane.is_mounted:
                pane.load_orders()

        app.run_worker(_cancel_and_report(), group="cancel-order", exclusive=False)
