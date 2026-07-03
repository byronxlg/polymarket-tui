"""Order entry modal: draft -> validate -> confirm -> place (dry-run by default)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Select, Static

from polymarket_tui.core import fmt
from polymarket_tui.core.config import Mode
from polymarket_tui.models.market import Event, Market, OrderBook
from polymarket_tui.services.orders import Issue, IssueLevel, OrderDraft, Side, Tif
from polymarket_tui.ui.widgets.confirm_modal import ConfirmModal


def parse_price(raw: str) -> Decimal | None:
    """Accept '0.123', '12.3c', or '12.3' (cents when > 1)."""
    raw = raw.strip().lower().rstrip("c").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value >= 1:
        value = value / 100
    return value


class OrderModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "cancel"),
        Binding("ctrl+s", "review", "review order"),
    ]

    DEFAULT_CSS = """
    OrderModal {
        align: center middle;
    }
    OrderModal > Vertical {
        width: 76;
        max-width: 95%;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    OrderModal #order-title {
        text-style: bold;
        margin-bottom: 1;
    }
    OrderModal .field-row {
        height: 3;
    }
    OrderModal Label {
        padding: 1 1 0 0;
        width: 9;
    }
    OrderModal Select {
        width: 22;
    }
    OrderModal Input {
        width: 22;
    }
    OrderModal #order-summary {
        margin-top: 1;
        height: auto;
    }
    OrderModal #order-issues {
        margin-top: 1;
        height: auto;
    }
    OrderModal #order-hint {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        market: Market,
        event: Event | None,
        outcome_index: int,
        side: Side,
        book: OrderBook | None,
    ) -> None:
        super().__init__()
        self._market = market
        self._event = event
        self._outcome_index = outcome_index
        self._side = side
        self._book = book

    # -- compose -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        outcomes = self._market.outcomes or ["Yes", "No"]
        mid = self._book.midpoint if self._book else None
        default_price = ""
        if mid is not None:
            default_price = f"{mid * 100:.1f}"
        with Vertical():
            yield Static(fmt.trunc(self._market.question, 70), id="order-title")
            with Horizontal(classes="field-row"):
                yield Label("side")
                yield Select(
                    [("BUY", "BUY"), ("SELL", "SELL")],
                    value=self._side.value,
                    allow_blank=False,
                    id="side-select",
                )
                yield Label("outcome")
                yield Select(
                    [(o, str(i)) for i, o in enumerate(outcomes[:2])],
                    value=str(self._outcome_index),
                    allow_blank=False,
                    id="outcome-select",
                )
            with Horizontal(classes="field-row"):
                yield Label("type")
                yield Select(
                    [("LIMIT", "LIMIT"), ("MARKET", "MARKET")],
                    value="LIMIT",
                    allow_blank=False,
                    id="type-select",
                )
                yield Label("tif")
                yield Select(
                    [(t.value, t.value) for t in Tif],
                    value=Tif.GTC.value,
                    allow_blank=False,
                    id="tif-select",
                )
            with Horizontal(classes="field-row"):
                yield Label("price")
                yield Input(value=default_price, placeholder="cents e.g. 12.3", id="price-input")
                yield Label("size")
                yield Input(placeholder="shares", id="size-input", type="number")
            yield Static("", id="order-summary")
            yield Static("", id="order-issues")
            yield Static(
                f"ctrl+s review   esc cancel   [{self.app.settings.mode.value} mode]",
                id="order-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#size-input", Input).focus()
        self._update_summary()

    # -- draft assembly --------------------------------------------------------

    def _current_draft(self) -> tuple[OrderDraft | None, str]:
        """(draft, error). Error is set when inputs are unparseable."""
        side = Side(self.query_one("#side-select", Select).value)
        outcome_index = int(self.query_one("#outcome-select", Select).value)
        is_market = self.query_one("#type-select", Select).value == "MARKET"
        tif = Tif(self.query_one("#tif-select", Select).value)

        token_id = self._market.token_id(outcome_index)
        if token_id is None:
            return None, "market has no token for that outcome"
        outcomes = self._market.outcomes or ["Yes", "No"]
        outcome_label = outcomes[outcome_index]

        if is_market:
            # Marketable limit at the touch; FAK so the remainder cancels.
            if self._book is None:
                return None, "no book snapshot for market order"
            touch = self._book.best_ask if side is Side.BUY else self._book.best_bid
            if touch is None:
                return None, "book is empty on that side"
            price = Decimal(str(touch.price))
            tif = Tif.FAK
        else:
            parsed = parse_price(self.query_one("#price-input", Input).value)
            if parsed is None:
                return None, "enter a price"
            price = parsed

        raw_size = self.query_one("#size-input", Input).value.strip()
        try:
            size = Decimal(raw_size)
        except InvalidOperation:
            return None, "enter a size"

        draft = OrderDraft(
            market=self._market,
            token_id=token_id,
            outcome_label=outcome_label,
            side=side,
            price=price,
            size=size,
            tif=tif,
            is_market_order=is_market,
        )
        return draft, ""

    def _update_summary(self) -> None:
        summary = self.query_one("#order-summary", Static)
        draft, error = self._current_draft()
        if draft is None:
            summary.update(Text(error, style="dim"))
            return
        out = Text()
        out.append(draft.summary() + "\n", style="bold")
        if draft.side is Side.BUY:
            payout = draft.size
            out.append(f"cost {fmt.money(float(draft.notional))}")
            out.append(
                f"  ->  pays {fmt.money(float(payout))} if {draft.outcome_label.upper()}",
                style="green",
            )
        else:
            out.append(f"proceeds {fmt.money(float(draft.notional))}")
        if self._book and self._book.midpoint is not None:
            out.append(f"   (mid {fmt.cents(self._book.midpoint)})", style="dim")
        summary.update(out)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_summary()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "type-select":
            self.query_one("#price-input", Input).disabled = event.value == "MARKET"
        self._update_summary()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_review()

    # -- review & place -----------------------------------------------------------

    def action_review(self) -> None:
        self.run_review()

    @work(exclusive=True, group="review")
    async def run_review(self) -> None:
        issues_widget = self.query_one("#order-issues", Static)
        draft, error = self._current_draft()
        if draft is None:
            issues_widget.update(Text(error, style="red"))
            return

        app = self.app
        try:
            cash = await app.portfolio.usdc_balance()
        except Exception:
            cash = None
        position = None
        if draft.side is Side.SELL:
            try:
                await app.portfolio.positions()
                pos = app.portfolio.position_for(draft.token_id)
                position = pos.size if pos else 0.0
            except Exception:
                position = None

        issues: list[Issue] = app.orders.validate(draft, self._book, cash, position)
        blocks = [i for i in issues if i.level is IssueLevel.BLOCK]
        warns = [i for i in issues if i.level is IssueLevel.WARN]

        report = Text()
        for issue in blocks:
            report.append(f"x {issue.message}\n", style="red")
        for issue in warns:
            report.append(f"! {issue.message}\n", style="yellow")
        issues_widget.update(report)
        if blocks:
            return

        body = Text()
        body.append(draft.summary() + "\n")
        body.append(fmt.trunc(self._market.question, 66) + "\n\n", style="dim")
        if draft.side is Side.BUY:
            body.append(f"cost            {fmt.money(float(draft.notional))}\n")
            body.append(
                f"payout if {draft.outcome_label.upper():<5} {fmt.money(float(draft.size))}\n"
            )
        else:
            body.append(f"proceeds        {fmt.money(float(draft.notional))}\n")
        if cash is not None:
            body.append(f"cash balance    {fmt.money(cash)}\n")
        for issue in warns:
            body.append(f"\n! {issue.message}", style="yellow")
        mode = app.settings.mode
        title = "REVIEW ORDER" + ("  [dry-run]" if mode is not Mode.TRADER_LIVE else "  [LIVE]")

        def _confirmed(ok: bool | None) -> None:
            if ok:
                self.place_order(draft)

        app.push_screen(ConfirmModal(title, body, "place order"), _confirmed)

    @work(exclusive=True, group="place")
    async def place_order(self, draft: OrderDraft) -> None:
        app = self.app
        result = await app.orders.place(draft)
        if result.ok and result.dry_run:
            self.notify(f"DRY RUN: {draft.summary()} signed, not posted", timeout=6)
        elif result.ok:
            app.portfolio.invalidate()
            status = result.status or "submitted"
            self.notify(f"Order {status}: {draft.summary()}", timeout=6)
        else:
            self.notify(result.error, severity="error", timeout=10)
            return
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
