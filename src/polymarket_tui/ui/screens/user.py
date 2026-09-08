"""Public trader profile: active positions, closed positions, recent activity.

Mirrors polymarket.com/@<name>: a header stats line, then Active (what they
hold now) and Closed (what they settled, with realized P&L).

Hosted as a drill pane by NavHost (30/70 split).
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane

from polymarket_tui.api.data import CLOSED_LIMIT, ProfileStats
from polymarket_tui.core import fmt
from polymarket_tui.core.links import market_url
from polymarket_tui.models.portfolio import ActivityItem, ClosedPosition, Position
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.staleness import RefreshOnReturn
from polymarket_tui.ui.tiers import ColumnSpec, Tier, TierAware, effective_tier, fit_columns
from polymarket_tui.ui.widgets.closed_table import ClosedTable
from polymarket_tui.ui.widgets.pnl_strip import PnlStrip
from polymarket_tui.ui.widgets.tables import (
    ACTIVITY_SPACIOUS_TIER_COLUMNS,
    ACTIVITY_TIER_COLUMNS,
    CLOSED_SPACIOUS_TIER_COLUMNS,
    CLOSED_TIER_COLUMNS,
    POSITIONS_SPACIOUS_TIER_COLUMNS,
    POSITIONS_TIER_COLUMNS,
    activity_row,
    closed_row,
    position_row,
    setup_activity_columns,
    setup_closed_columns,
    setup_positions_columns,
)
from polymarket_tui.ui.widgets.vim_table import VimDataTable

# (tab pane id, table id) in tab order.
PANES: tuple[tuple[str, str], ...] = (
    ("pane-user-positions", "#user-positions"),
    ("pane-user-closed", "#user-closed"),
    ("pane-user-activity", "#user-activity"),
)


class UserPane(RefreshOnReturn, TierAware, Vertical):
    """Public trader profile - a drill pane."""

    header_title = "trader"

    BINDINGS = [
        Binding("escape", "app.nav_back", "back"),
        Binding("space", "toggle_watch", "watch user"),
        Binding("tab", "next_pane", "pane"),
        Binding("shift+tab", "prev_pane", "prev pane", show=False),
    ]

    def __init__(self, address: str, name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._address = address
        self._trader_name = name
        # Kept so a tier change can re-render the tables without refetching.
        self._positions: list[Position] = []
        self._closed_positions: list[ClosedPosition] = []
        self._activity: list[ActivityItem] = []
        # Fitted column specs after width fitting.
        self._pos_spec: list[ColumnSpec] = list(POSITIONS_TIER_COLUMNS["full"])
        self._closed_spec: list[ColumnSpec] = list(CLOSED_TIER_COLUMNS["full"])
        self._act_spec: list[ColumnSpec] = list(ACTIVITY_TIER_COLUMNS["full"])
        self._rendered_density: str = "condensed"
        self._stats: ProfileStats | None = None
        self.drill_key = ("user", address)

    def compose(self) -> ComposeResult:
        yield Static(self._title_line(), classes="screen-title", id="user-title")
        yield Static(id="user-stats")
        with TabbedContent(id="user-tabs"):
            with TabPane("Active", id="pane-user-positions"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="user-positions")
            with TabPane("Closed", id="pane-user-closed"):
                yield ClosedTable(cursor_type="row", zebra_stripes=True, id="user-closed")
                yield Static(id="user-closed-note")
            with TabPane("History", id="pane-user-activity"):
                yield VimDataTable(cursor_type="row", zebra_stripes=True, id="user-activity")
        yield PnlStrip(id="user-pnl")

    def focus_inner(self) -> None:
        table_id = dict(PANES).get(self._active_pane(), "#user-positions")
        self.query_one(table_id, VimDataTable).focus()

    def _title_line(self) -> Text:
        # A Text, not a markup string: the trader name is a user-set display
        # name from the API and a '[' in it would crash the Static's markup
        # parser (see the balance-line 502). This line carries no markup.
        watched = " | watched" if self.app.watchlist.is_watched_user(self._address) else ""
        return Text(f"{self._trader_name}  |  {self._address[:6]}...{self._address[-4:]}{watched}")

    def _pos_columns(self) -> dict[Tier, tuple]:
        """Positions column sets for the current density (spacious re-composes rows)."""
        if self.app.density == "spacious":
            return POSITIONS_SPACIOUS_TIER_COLUMNS
        return POSITIONS_TIER_COLUMNS

    def _closed_columns(self) -> dict[Tier, tuple]:
        """Closed-positions column sets for the current density."""
        if self.app.density == "spacious":
            return CLOSED_SPACIOUS_TIER_COLUMNS
        return CLOSED_TIER_COLUMNS

    def _act_columns(self) -> dict[Tier, tuple]:
        """Activity column sets for the current density (spacious re-composes rows)."""
        if self.app.density == "spacious":
            return ACTIVITY_SPACIOUS_TIER_COLUMNS
        return ACTIVITY_TIER_COLUMNS

    def on_mount(self) -> None:
        self.query_one("#user-stats", Static).display = False
        self.query_one("#user-closed-note", Static).display = False
        self._rendered_density = self.app.density
        self._pos_spec = list(self._pos_columns()[self.tier])
        self._closed_spec = list(self._closed_columns()[self.tier])
        self._act_spec = list(self._act_columns()[self.tier])
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
        closed = self.query_one("#user-closed", ClosedTable)
        closed.clear(columns=True)
        setup_closed_columns(closed, columns=self._closed_spec)
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
        # The tables live in tabs (the hidden ones measure 0 wide), so fit
        # all three against the pane's own width after layout settles.
        self.call_after_refresh(self._refit)

    def _refit(self) -> None:
        if not alive(self):
            return  # call_after_refresh can fire after the pane is torn down
        # Both are context, not the primary list: they go at compact.
        self._apply_stats_visibility()
        self._render_closed_note()
        width = self.size.width - 3  # border + the tables' vertical scrollbar
        if width <= 0:
            return
        pos_columns = self._pos_columns()
        closed_columns = self._closed_columns()
        act_columns = self._act_columns()
        pos_tier = effective_tier(self.tier, width, pos_columns)
        closed_tier = effective_tier(self.tier, width, closed_columns)
        act_tier = effective_tier(self.tier, width, act_columns)
        pos_flex = max((len(p.title) for p in self._positions), default=0) or None
        closed_flex = max((len(p.title) for p in self._closed_positions), default=0) or None
        act_flex = max((len(i.title) for i in self._activity), default=0) or None
        pos_spec = fit_columns(pos_columns[pos_tier], width, "market", pos_flex)
        closed_spec = fit_columns(closed_columns[closed_tier], width, "market", closed_flex)
        act_spec = fit_columns(act_columns[act_tier], width, "market", act_flex)
        if (pos_spec, closed_spec, act_spec) == (
            self._pos_spec,
            self._closed_spec,
            self._act_spec,
        ) and self._rendered_density == self.app.density:
            return
        self._pos_spec, self._closed_spec, self._act_spec = pos_spec, closed_spec, act_spec
        self._rendered_density = self.app.density
        self._build_columns()
        self._render_tables()

    def _render_tables(self) -> None:
        density = self.app.density
        height = 2 if density == "spacious" else 1

        positions_table = self.query_one("#user-positions", VimDataTable)
        positions_table.clear()
        for pos in sorted(self._positions, key=lambda p: p.current_value, reverse=True):
            # Resolved losses are dust, not holdings - same filter as the
            # portfolio table (Byron, UX audit 2026-07-06). The profile no
            # longer drops them on the floor: once a position settles it
            # appears under Closed with its realized loss.
            if pos.size < 0.01 or pos.resolved_loss:
                continue
            positions_table.add_row(
                *position_row(pos, columns=self._pos_spec, density=density),
                key=f"{pos.slug}|{pos.asset}",
                height=height,
            )

        closed_table = self.query_one("#user-closed", ClosedTable)
        closed_table.clear()
        urls: dict[str, str] = {}
        # Already most-recently-closed first from the API - do not re-sort.
        for pos in self._closed_positions:
            key = f"{pos.slug}|{pos.asset}"
            urls[key] = market_url(pos.event_slug, pos.slug)
            closed_table.add_row(
                *closed_row(pos, columns=self._closed_spec, density=density),
                key=key,
                height=height,
            )
        closed_table.set_web_urls(urls)

        activity_table = self.query_one("#user-activity", VimDataTable)
        activity_table.clear()
        for i, item in enumerate(self._activity):
            activity_table.add_row(
                *activity_row(
                    item, compact_size=True, columns=self._act_spec, density=density
                ),
                key=f"{i}|{item.slug}",
                height=height,
            )
        self._render_closed_note()

    def _closed_truncated(self) -> bool:
        """A read that filled the cap is a cap, not the end of the history -
        an active trader settles hundreds of positions."""
        return len(self._closed_positions) >= CLOSED_LIMIT

    def _render_closed_note(self) -> None:
        note = self.query_one("#user-closed-note", Static)
        truncated = self._closed_truncated()
        # Compact tier is context-only, and inline display flags override
        # stylesheet rules, so the tier gate lives here (as for #lost-note).
        note.display = truncated and self.tier != "compact"
        if truncated:
            note.update(
                Text(f"showing the {CLOSED_LIMIT} most recently closed", style="dim")
            )

    @work(exclusive=True)
    async def load_user(self) -> None:
        app = self.app
        try:
            self._stats = await app.data.profile_stats(self._address)
        except Exception:
            self._stats = None
        if alive(self):
            self._render_stats()

        try:
            self._positions = await app.data.positions(self._address)
        except Exception as exc:
            self.notify(f"positions unavailable: {exc}", severity="error")
            self._positions = []
        try:
            self._closed_positions = await app.data.closed_positions(self._address)
        except Exception:
            self._closed_positions = []
        try:
            self._activity = await app.data.activity(self._address, limit=60)
        except Exception:
            self._activity = []
        if not alive(self):
            return  # pane torn down while we fetched
        self._render_tables()
        self._schedule_refit()  # loaded titles set the flex column width

    def _stats_parts(self) -> list[str]:
        """The profile header numbers, in the reading order the web page uses.
        A field whose service did not answer is dropped, not shown as '-'."""
        stats = self._stats
        if stats is None:
            return []
        parts = []
        if stats.value is not None:
            parts.append(f"positions {fmt.money(stats.value)}")
        if stats.profit is not None:
            parts.append(f"profit {stats.profit:+,.2f}")
        if stats.volume is not None:
            parts.append(f"volume {fmt.vol(stats.volume)}")
        if stats.markets_traded is not None:
            parts.append(f"{stats.markets_traded:,} markets")
        return parts

    def _render_stats(self) -> None:
        self.query_one("#user-stats", Static).update("  ·  ".join(self._stats_parts()))
        self._apply_stats_visibility()

    def _apply_stats_visibility(self) -> None:
        line = self.query_one("#user-stats", Static)
        # Inline display flags override stylesheet rules, so the tier gate for
        # this line lives here rather than in app.tcss (same as #lost-note).
        line.display = bool(self._stats_parts()) and self.tier != "compact"

    def _active_pane(self) -> str:
        return self.query_one(TabbedContent).active

    def on_data_table_row_selected(self, event) -> None:
        key = str(event.row_key.value)
        pane = self._active_pane()
        if pane == "pane-user-activity":
            slug = key.split("|", 1)[1] if "|" in key else ""  # keys are "index|slug"
            self.open_market_by_slug(slug)
            return
        slug, _, asset = key.partition("|")  # active and closed key as "slug|asset"
        if pane == "pane-user-closed":
            # Settled markets often miss the slug lookup - carry the condition
            # id from the row so the drill still lands.
            pos = next((p for p in self._closed_positions if p.asset == asset), None)
            self.open_market_by_slug(slug, pos.condition_id if pos else "")
            return
        self.open_market_by_slug(slug)

    @work(exclusive=True, group="open-market")
    async def open_market_by_slug(self, slug: str, condition_id: str = "") -> None:
        if not slug and not condition_id:
            return
        try:
            market = await self.app.gamma.market_by_slug(slug) if slug else None
            if market is None and condition_id:
                market = await self.app.gamma.market_by_condition(condition_id)
        except Exception as exc:
            self.notify(f"could not open market: {exc}", severity="error")
            return
        if market is None:
            # Gamma delists resolved markets, so most Closed rows land here.
            # Say so instead of leaving enter looking broken.
            self.notify("Market is no longer listed (resolved) - o opens it on the web")
            return
        self.app.open_market(market)

    def action_toggle_watch(self) -> None:
        watched = self.app.watchlist.toggle_user(self._address, self._trader_name)
        self.notify(f"{'Watching' if watched else 'Unwatched'} {self._trader_name}", timeout=3)
        # Following changes nothing about the trader's data - update the
        # title only, no refetch of stats/positions/activity.
        self.query_one("#user-title", Static).update(self._title_line())

    def _step_pane(self, delta: int) -> None:
        tabbed = self.query_one(TabbedContent)
        ids = [pane_id for pane_id, _ in PANES]
        idx = (ids.index(tabbed.active) + delta) % len(ids) if tabbed.active in ids else 0
        tabbed.active = ids[idx]
        self.query_one(dict(PANES)[ids[idx]], VimDataTable).focus()

    def action_next_pane(self) -> None:
        self._step_pane(1)

    def action_prev_pane(self) -> None:
        self._step_pane(-1)

    def action_refresh(self) -> None:
        self.load_user()
