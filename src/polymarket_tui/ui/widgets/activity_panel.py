"""Market activity / comments panel, shown below the chart on market screens.

`a` shows live trades (polled), `c` shows event comments; pressing the active
view's key again hides the panel.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rich.text import Text
from textual import work
from textual.containers import VerticalScroll
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.theme import BLUE, DOWN, UP

TRADES_POLL_SECONDS = 5.0


def _ago(dt: datetime) -> str:
    if dt.tzinfo is None:
        # API timestamps are UTC; a naive parse must not TypeError the
        # aware-minus-naive subtraction below.
        dt = dt.replace(tzinfo=UTC)
    seconds = (datetime.now(UTC) - dt).total_seconds()
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.0f}h"
    return f"{seconds / 86400:.0f}d"


class ActivityPanel(VerticalScroll):
    DEFAULT_CSS = """
    ActivityPanel {
        height: 40%;
        min-height: 8;
        border-top: solid $panel-lighten-2;
        padding: 0 1;
        display: none;
    }
    ActivityPanel.open {
        display: block;
    }
    """

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(Static(id="activity-body"), **kwargs)
        self._market: Market | None = None
        self._event: Event | None = None
        self._mode: str | None = None  # "trades" | "comments" | None (hidden)

    def on_mount(self) -> None:
        self.set_interval(TRADES_POLL_SECONDS, self._poll)

    def configure(self, market: Market | None, event: Event | None) -> None:
        """market may be None on the event pane - comments are event-level."""
        self._market = market
        self._event = event

    @property
    def mode(self) -> str | None:
        return self._mode

    def toggle(self, mode: str) -> None:
        if self._mode == mode:
            self._mode = None
            self.remove_class("open")
            return
        self._mode = mode
        self.add_class("open")
        self.query_one("#activity-body", Static).update(Text("loading...", style="dim"))
        self.refresh_content()

    def _poll(self) -> None:
        if self._mode == "trades":
            self.refresh_content()

    @work(exclusive=True, group="activity")
    async def refresh_content(self) -> None:
        if not alive(self):
            return  # the poll interval can fire in the teardown window
        if self._mode == "trades":
            await self._load_trades()
        elif self._mode == "comments":
            await self._load_comments()

    async def _load_trades(self) -> None:
        body = self.query_one("#activity-body", Static)
        if self._market is None or not self._market.condition_id:
            body.update(Text("no market id for trades", style="dim"))
            return
        try:
            trades = await self.app.data.market_trades(self._market.condition_id)
        except Exception as exc:
            if alive(self):
                body.update(Text(f"trades unavailable: {exc}", style="dim"))
            return
        if not alive(self):
            return  # host pane torn down while we fetched
        out = Text()
        out.append(
            f"LIVE TRADES  (refreshes {TRADES_POLL_SECONDS:.0f}s, a to hide)\n", style="bold"
        )
        for trade in trades:
            out.append(f"{trade.when.astimezone().strftime('%H:%M:%S')} ", style="dim")
            out.append(f"{trade.side:<4}", style=UP if trade.side == "BUY" else DOWN)
            out.append(f" {trade.size:>8,.0f} {fmt.trunc(trade.outcome, 10):<10}")
            out.append(f" @ {fmt.cents(trade.price):>6}", style="bold")
            out.append(f"  {fmt.money(trade.usdc_size):>9}" if trade.usdc_size else " " * 11)
            out.append(f"  {fmt.trunc(trade.trader, 20)}\n", style="dim")
        if not trades:
            out.append("no recent trades\n", style="dim")
        body.update(out)

    async def _load_comments(self) -> None:
        body = self.query_one("#activity-body", Static)
        if self._event is None or not self._event.id:
            body.update(Text("comments live on the event - none linked here", style="dim"))
            return
        # Recurring/grouped events (Fed, daily Bitcoin, World Cup matches) thread
        # their comments on the series, not the daily event; standalone events
        # keep the comments on the event itself. See GammaClient.comments.
        series = self._event.primary_series
        try:
            if series and series.id:
                comments = await self.app.gamma.comments(series.id, entity_type="Series")
            else:
                comments = await self.app.gamma.comments(self._event.id)
        except Exception as exc:
            if alive(self):
                body.update(Text(f"comments unavailable: {exc}", style="dim"))
            return
        if not alive(self):
            return  # host pane torn down while we fetched
        out = Text()
        out.append("COMMENTS  (newest first, c to hide)\n", style="bold")
        for comment in comments:
            profile = comment.get("profile") or {}
            name = profile.get("name") or profile.get("pseudonym") or "anon"
            created = str(comment.get("createdAt") or "")  # null-safe
            when = ""
            try:
                when = _ago(datetime.fromisoformat(created.replace("Z", "+00:00")))
            except ValueError:
                pass
            out.append(f"{fmt.trunc(name, 22)} ", style=BLUE)
            out.append(f"{when}\n", style="dim")
            text = (comment.get("body") or "").strip().replace("\n", " ")
            out.append(f"  {fmt.trunc(text, 400)}\n", style="")
        if not comments:
            out.append("no comments yet\n", style="dim")
        body.update(out)
