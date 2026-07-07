"""Market activity / comments panel, shown below the chart on market screens.

`c` shows event comments; pressing `c` again hides the panel. Comments are a
focusable, cursored list (up/down to move, right/enter to open the author's
profile). A polled live-trades text mode also exists but is not currently
bound to a key on either screen.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import Event, Market
from polymarket_tui.ui.liveness import alive
from polymarket_tui.ui.theme import DOWN, UP
from polymarket_tui.ui.widgets.comment_list import CommentList

TRADES_POLL_SECONDS = 5.0


class ActivityPanel(Vertical):
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
    ActivityPanel #activity-scroll {
        height: 100%;
    }
    ActivityPanel CommentList {
        height: 100%;
        background: transparent;
        border: none;
        padding: 0;
        scrollbar-size-vertical: 1;
    }
    ActivityPanel CommentList > .option-list--option {
        padding: 0 1 1 1;
    }
    /* Cursor legible in both states; $primary tint adapts to the active theme. */
    ActivityPanel CommentList > .option-list--option-highlighted {
        background: $primary 8%;
    }
    ActivityPanel CommentList:focus > .option-list--option-highlighted {
        background: $primary 18%;
    }
    """

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._market: Market | None = None
        self._event: Event | None = None
        self._mode: str | None = None  # "trades" | "comments" | None (hidden)

    def compose(self):
        yield VerticalScroll(Static(id="activity-body"), id="activity-scroll")
        yield CommentList(id="activity-comments")

    def on_mount(self) -> None:
        self.query_one("#activity-comments", CommentList).display = False
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
            self.close()
            return
        self._mode = mode
        self.add_class("open")
        self._show_text(Text("loading...", style="dim"))
        self.refresh_content()

    def close(self) -> None:
        self._mode = None
        self.remove_class("open")

    def focus_list(self) -> None:
        clist = self.query_one("#activity-comments", CommentList)
        if clist.display and clist.option_count:
            clist.focus()

    def _show_text(self, content: Text) -> None:
        """Route status/trade text to the scroll surface; hide the comment list."""
        self.query_one("#activity-comments", CommentList).display = False
        self.query_one("#activity-scroll", VerticalScroll).display = True
        self.query_one("#activity-body", Static).update(content)

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
        if self._market is None or not self._market.condition_id:
            self._show_text(Text("no market id for trades", style="dim"))
            return
        try:
            trades = await self.app.data.market_trades(self._market.condition_id)
        except Exception as exc:
            if alive(self):
                self._show_text(Text(f"trades unavailable: {exc}", style="dim"))
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
        self._show_text(out)

    async def _load_comments(self) -> None:
        if self._event is None or not self._event.id:
            self._show_text(Text("comments live on the event - none linked here", style="dim"))
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
                self._show_text(Text(f"comments unavailable: {exc}", style="dim"))
            return
        if not alive(self) or self._mode != "comments":
            return  # host pane torn down, or toggled away, while we fetched
        if not comments:
            self._show_text(Text("no comments yet", style="dim"))
            return
        clist = self.query_one("#activity-comments", CommentList)
        self.query_one("#activity-scroll", VerticalScroll).display = False
        clist.display = True
        clist.set_comments(comments)
        clist.focus()
