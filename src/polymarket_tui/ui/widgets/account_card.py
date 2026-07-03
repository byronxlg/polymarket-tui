"""Account card for the home screen: who you are, balances, top positions."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.widgets import Static

from polymarket_tui.core import fmt

REFRESH_SECONDS = 60.0
TOP_POSITIONS = 4


class AccountCard(Static):
    DEFAULT_CSS = """
    AccountCard {
        height: auto;
        padding: 0 0 1 0;
        border-bottom: solid $panel-lighten-2;
        margin-bottom: 1;
    }
    """

    def on_mount(self) -> None:
        self.refresh_card()
        self.set_interval(REFRESH_SECONDS, self.refresh_card)

    @work(exclusive=True, group="account-card")
    async def refresh_card(self) -> None:
        app = self.app
        settings = app.settings
        out = Text()
        if not settings.can_read_portfolio:
            out.append("not signed in\n", style="bold")
            out.append("press A to authenticate", style="dim")
            self.update(out)
            return

        funder = settings.polymarket_funder
        if app.username is None:
            try:
                app.username = await app.gamma.public_profile_name(funder)
            except Exception:
                pass
        name = app.username or f"{funder[:6]}...{funder[-4:]}"
        out.append(f"{name}\n", style="bold")

        cash = value = None
        try:
            if app.authed is not None:
                cash = await app.portfolio.usdc_balance()
            value = await app.portfolio.portfolio_value()
        except Exception:
            pass
        if cash is not None:
            out.append("cash      ", style="dim")
            out.append(f"${cash:,.2f}\n")
        if value is not None:
            out.append("positions ", style="dim")
            out.append(f"${value:,.2f}\n")
        if cash is not None and value is not None:
            out.append("total     ", style="dim")
            out.append(f"${cash + value:,.2f}\n", style="bold")

        try:
            positions = [p for p in await app.portfolio.positions() if p.size >= 0.01]
        except Exception:
            positions = []
        if positions:
            out.append("\n")
            top = sorted(positions, key=lambda p: p.current_value, reverse=True)
            for pos in top[:TOP_POSITIONS]:
                pnl_style = "green" if pos.cash_pnl > 0 else "red" if pos.cash_pnl < 0 else "dim"
                out.append(f"{fmt.trunc(pos.title, 22):<23}", style="")
                out.append(f"{fmt.money(pos.current_value):>8}")
                out.append(f" {pos.cash_pnl:+,.1f}\n", style=pnl_style)
            if len(positions) > TOP_POSITIONS:
                out.append(f"... {len(positions) - TOP_POSITIONS} more (p)\n", style="dim")
        try:
            orders = await app.portfolio.open_orders()
            if orders:
                out.append(f"\n{len(orders)} open order(s)", style="yellow")
        except Exception:
            pass
        self.update(out)
