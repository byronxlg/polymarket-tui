"""Shared trader overview: value + top positions for an address.

Used by the search screen's traders mode and the market screen's expanded
trades view - one rendering for "who is this trader" everywhere.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.ui.widgets.tables import pnl_text

TOP_POSITIONS = 8


class TraderOverview(Static):
    def show_trader(self, address: str, name: str, bio: str | None = None) -> None:
        head = Text()
        head.append(name + "\n", style="bold")
        head.append(f"{address[:8]}...{address[-6:]}\n", style="dim")
        if bio:
            head.append(fmt.trunc(bio, 120) + "\n", style="dim")
        self.update(head)
        self._load(address, head)

    @work(exclusive=True, group="trader-overview")
    async def _load(self, address: str, head: Text) -> None:
        out = head.copy()
        try:
            value = await self.app.data.portfolio_value(address)
            positions = await self.app.data.positions(address, limit=50)
        except Exception:
            out.append("\n(positions unavailable)", style="dim")
            self.update(out)
            return
        out.append("\npositions ", style="dim")
        out.append(f"${value or 0:,.2f}\n\n", style="bold")
        top = sorted(
            (p for p in positions if p.size >= 0.01),
            key=lambda p: p.current_value,
            reverse=True,
        )
        for pos in top[:TOP_POSITIONS]:
            out.append(f"{fmt.trunc(pos.title, 24):<25}")
            out.append(f"{fmt.money(pos.current_value):>8} ")
            out.append_text(pnl_text(pos.cash_pnl, pos.percent_pnl))
            out.append("\n")
        if not top:
            out.append("no open positions\n", style="dim")
        self.update(out)
