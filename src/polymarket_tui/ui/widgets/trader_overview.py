"""Shared trader overview: value + top positions for an address.

Used by the search screen's traders mode and the market screen's expanded
trades view - one rendering for "who is this trader" everywhere. Loaded data
is cached so re-renders (cursor moves, resizes) never refetch; truncation
widths follow the rendered width.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.ui.widgets.tables import pnl_text

TOP_POSITIONS = 8


class TraderOverview(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._address: str | None = None
        self._name = ""
        self._bio: str | None = None
        self._value: float | None = None
        self._top: list | None = None  # None = loading, [] = loaded empty
        self._status = ""

    def show_trader(self, address: str, name: str, bio: str | None = None) -> None:
        if address == self._address:
            return  # already showing (or loading) this trader
        self._address, self._name, self._bio = address, name, bio
        self._value, self._top, self._status = None, None, ""
        self._render()
        self._load(address)

    def on_resize(self) -> None:
        if self._address is not None:
            self._render()

    @work(exclusive=True, group="trader-overview")
    async def _load(self, address: str) -> None:
        try:
            value = await self.app.data.portfolio_value(address)
            positions = await self.app.data.positions(address, limit=50)
        except Exception:
            value, positions = None, None
        if address != self._address:
            return  # the cursor moved on while we fetched
        if positions is None:
            self._status = "(positions unavailable)"
        else:
            self._value = value
            self._top = sorted(
                (p for p in positions if p.size >= 0.01),
                key=lambda p: p.current_value,
                reverse=True,
            )[:TOP_POSITIONS]
        self._render()

    def _render(self) -> None:
        w = max(24, self.size.width or 44)
        out = Text()
        out.append(self._name + "\n", style="bold")
        if self._address:
            out.append(f"{self._address[:8]}...{self._address[-6:]}\n", style="dim")
        if self._bio:
            out.append(fmt.trunc(self._bio, 2 * w) + "\n", style="dim")
        if self._status:
            out.append(f"\n{self._status}", style="dim")
            self.update(out)
            return
        if self._top is None:
            self.update(out)
            return
        out.append("\npositions ", style="dim")
        out.append(f"${self._value or 0:,.2f}\n\n", style="bold")
        # Name column fills what the value (8) + P&L (~12) columns leave.
        name_w = max(12, w - 22)
        for pos in self._top:
            out.append(f"{fmt.trunc(pos.title, name_w):<{name_w + 1}}")
            out.append(f"{fmt.money(pos.current_value):>8} ")
            out.append_text(pnl_text(pos.cash_pnl, pos.percent_pnl))
            out.append("\n")
        if not self._top:
            out.append("no open positions\n", style="dim")
        self.update(out)
