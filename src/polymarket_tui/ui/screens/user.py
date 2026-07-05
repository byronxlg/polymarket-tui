"""Public trader profile: positions and recent activity for any address.

Hosted as a drill pane by NavHost (30/70 split).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import ActivityItem, Position
from polymarket_tui.ui.tiers import ColumnSpec, Tier, TierAware, effective_tier, fit_columns
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


class UserPane(TierAware, Vertical):
    """Public trader profile - a drill pane."""

    header_title = "trader"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "toggle_watch", "watch user"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "next_pane", "prev pane", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]

    def __init__(self, address: str, name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._address = address
        self._name = name
        # Kept so a tier change can re-render the tables without refetching.
        self._positions: list[Position] = []
        self._activity: list[ActivityItem] = []
        # Fitted (positions, activity) column specs after width fitting.
        self._pos_spec: list[ColumnSpec] = list(POSITIONS_TIER_COLUMNS["full"])
        self._act_spec: list[ColumnSpec] = list(ACTIVITY_TIER_COLUMNS["full"])
        self._rendered_density: str = "condensed"
        self.drill_key = ("user", address)

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title", id="user-title")
        with TabbedContent(id="user-tabs"):
            with TabPane("Positions", id="pane-user-positions"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="user-positions")
            with TabPane("Activity", id="pane-user-activity"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="user-activity")
        yield PnlStrip(id="user-pnl")

    def focus_inner(self) -> None:
        self.query_one("#user-positions", VimDataTable).focus()

    def _title_line(self) -> str:
        watched = " | watched" if self.app.watchlist.is_watched_user(self._address) else ""
        return f"{self._name}  |  {self._address[:6]}...{self._address[-4:]}{watched}"

    def _pos_columns(self) -> dict[Tier, tuple]:
        """Positions column sets for the current density (spacious re-composes rows)."""
        if self.app.density == "spacious":
            return POSITIONS_SPACIOUS_TIER_COLUMNS
        return POSITIONS_TIER_COLUMNS

    def on_mount(self) -> None:
        self._rendered_density = self.app.density
        self._pos_spec = list(self._pos_columns()[self.tier])
        self._act_spec = list(ACTIVITY_TIER_COLUMNS[self.tier])
        self._build_columns()
        for tabs in self.query("Tabs"):
            tabs.can_focus = False
        self.query_one("#user-positions", VimDataTable).focus()
        self.load_user()
        self.query_one(PnlStrip).show_user(self._address)
        self.tier_ready()
        self._schedule_refit()

    def _build_columns(self) -> None:
        positions = self.query_one("#user-positions", VimDataTable)
        positions.clear(columns=True)
        setup_positions_columns(positions, columns=self._pos_spec)
        activity = self.query_one("#user-activity", VimDataTable)
        activity.clear(columns=True)
        setup_activity_columns(activity, columns=self._act_spec)

    def on_tier_changed(self, tier: Tier) -> None:
        self._schedule_refit()

    def on_density_changed(self, density: str) -> None:
        """T toggled: positions re-compose into two-line rows (app calls this)."""
        self._schedule_refit()

    def on_resize(self) -> None:
        if self._tier_ready:
            self._schedule_refit()

    def _schedule_refit(self) -> None:
        # The tables live in tabs (the hidden one measures 0 wide), so fit
        # both against the pane's own width after layout settles.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        width = self.size.width - 2  # border + slack
        if width <= 0:
            return
        pos_columns = self._pos_columns()
        pos_tier = effective_tier(self.tier, width, pos_columns)
        act_tier = effective_tier(self.tier, width, ACTIVITY_TIER_COLUMNS)
        pos_flex = max((len(p.title) for p in self._positions), default=0) or None
        act_flex = max((len(i.title) for i in self._activity), default=0) or None
        pos_spec = fit_columns(pos_columns[pos_tier], width, "market", pos_flex)
        act_spec = fit_columns(ACTIVITY_TIER_COLUMNS[act_tier], width, "market", act_flex)
        if (pos_spec, act_spec) == (
            self._pos_spec,
            self._act_spec,
        ) and self._rendered_density == self.app.density:
            return
        self._pos_spec, self._act_spec = pos_spec, act_spec
        self._rendered_density = self.app.density
        self._build_columns()
        self._render_tables()

    def _render_tables(self) -> None:
        positions_table = self.query_one("#user-positions", VimDataTable)
        positions_table.clear()
        density = self.app.density
        height = 2 if density == "spacious" else 1
        for pos in sorted(self._positions, key=lambda p: p.current_value, reverse=True):
            if pos.size < 0.01:
                continue
            positions_table.add_row(
                *position_row(pos, columns=self._pos_spec, density=density),
                key=f"{pos.slug}|{pos.asset}",
                height=height,
            )
        activity_table = self.query_one("#user-activity", VimDataTable)
        activity_table.clear()
        for i, item in enumerate(self._activity):
            activity_table.add_row(
                *activity_row(item, compact_size=True, columns=self._act_spec),
                key=f"{i}|{item.slug}",
            )

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

        try:
            self._positions = await app.data.positions(self._address)
        except Exception as exc:
            self.notify(f"positions unavailable: {exc}", severity="error")
            self._positions = []
        try:
            self._activity = await app.data.activity(self._address, limit=60)
        except Exception:
            self._activity = []
        self._render_tables()
        self._schedule_refit()  # loaded titles set the flex column width

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
