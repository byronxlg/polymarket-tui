"""Profit-history strip: title line + cumulative P&L line chart.

One rendering of "how has this account done" shared by the portfolio
screen (your own wallet) and the trader profile (anyone else's).
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.containers import Vertical
from textual.widgets import Static

from polymarket_tui.models.market import PricePoint
from polymarket_tui.ui.theme import DOWN, UP
from polymarket_tui.ui.widgets.linechart import render_chart

# rgb tuples for the line chart, matching theme UP/DOWN
GREEN = (63, 207, 142)
RED = (248, 113, 122)


class PnlStrip(Vertical):
    DEFAULT_CSS = """
    PnlStrip {
        border: solid $panel-lighten-2;
        padding: 0 1;
    }
    PnlStrip > .pnl-title {
        height: 1;
    }
    PnlStrip > .pnl-chart {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._points: list[PricePoint] = []

    def compose(self):
        yield Static(classes="pnl-title")
        yield Static(classes="pnl-chart")

    def on_resize(self) -> None:
        self._draw()

    def show_user(self, address: str) -> None:
        """Fetch and render the profit history for a wallet address."""
        self._load(address)

    @work(exclusive=True, group="pnl-strip")
    async def _load(self, address: str) -> None:
        try:
            points = await self.app.data.user_pnl(address)
        except Exception:
            points = []
        self.show_points(points)

    def show_points(self, points: list[PricePoint]) -> None:
        self._points = points
        title = self.query_one(".pnl-title", Static)
        if len(points) >= 2:
            latest, first = points[-1].p, points[0].p
            delta = latest - first
            style = UP if delta >= 0 else DOWN
            text = Text()
            text.append("ALL-TIME PROFIT  ", style="bold")
            text.append(f"${latest:,.2f}", style="bold")
            text.append(f"   {delta:+,.2f}", style=style)
            text.append(" last 30d", style="dim")
            title.update(text)
        else:
            title.update(Text("ALL-TIME PROFIT  (no history yet)", style="dim"))
        self._draw()

    def _draw(self) -> None:
        chart = self.query_one(".pnl-chart", Static)
        points = self._points
        if len(points) < 2:
            chart.update(Text(""))
            return
        size = chart.size
        if size.width < 12 or size.height < 4:
            return
        # render_chart plots p*100, so feed dollars/100 to label the axis in dollars.
        scaled = [PricePoint(t=pt.t, p=pt.p / 100) for pt in points]
        color = GREEN if points[-1].p >= points[0].p else RED
        chart.update(
            render_chart(
                [(scaled, color)],
                width=size.width,
                height=size.height + 1,  # no separate axis row budgeted; keep compact
                time_format="%b %d",
                clamp=None,
            )
        )
