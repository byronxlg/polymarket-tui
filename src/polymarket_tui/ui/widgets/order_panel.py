"""Inline order entry, shown below the live order book on the market screen.

Keyboard-first: b/s opens it preset to a side, price/size are the only two
fields (empty price = market order at the touch), up/down bump the price by
one tick, enter advances price -> size -> review, and confirmation is a plain
'y' in the same panel - the book stays visible and live the whole time.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Label, Static

from polymarket_tui.core import fmt
from polymarket_tui.core.config import Mode
from polymarket_tui.models.market import Market, OrderBook
from polymarket_tui.services.orders import (
    IssueLevel,
    OrderDraft,
    ReconcileTarget,
    Side,
    Tif,
    parse_price,
    round_to_tick,
    tick_size,
)
from polymarket_tui.ui.widgets.confirm_modal import ConfirmModal

TIF_CYCLE = [Tif.GTC, Tif.FOK, Tif.FAK]


class SideKey(Message):
    """b/s/space pressed inside an order field: pick or toggle (None) the side."""

    def __init__(self, side: Side | None) -> None:
        super().__init__()
        self.side = side


class _SideSwitchingInput(Input):
    """b/s never mean text in these numeric fields - they flip the side."""

    async def _on_key(self, event) -> None:
        if event.character in ("b", "B"):
            event.stop()
            event.prevent_default()
            self.post_message(SideKey(Side.BUY))
            return
        if event.character in ("s", "S"):
            event.stop()
            event.prevent_default()
            self.post_message(SideKey(Side.SELL))
            return
        if event.character == " ":
            # space = the contextual toggle: flip BUY/SELL while ordering
            event.stop()
            event.prevent_default()
            self.post_message(SideKey(None))
            return
        if event.key == "left" and self.cursor_position == 0:
            # left at the start of the field steps out: close the panel
            event.stop()
            event.prevent_default()
            self.post_message(self.CloseRequested())
            return
        await super()._on_key(event)

    class CloseRequested(Message):
        pass


class PriceInput(_SideSwitchingInput):
    """Price field: up/down bump by one market tick."""

    BINDINGS = [
        Binding("up", "bump(1)", "tick up", show=False),
        Binding("down", "bump(-1)", "tick down", show=False),
        Binding("shift+up", "bump(10)", "10 ticks up", show=False),
        Binding("shift+down", "bump(-10)", "10 ticks down", show=False),
    ]

    class Bumped(Message):
        def __init__(self, direction: int) -> None:
            super().__init__()
            self.direction = direction

    def action_bump(self, direction: int) -> None:
        self.post_message(self.Bumped(direction))


class SizeInput(_SideSwitchingInput):
    """Size field: up/down bump by one share, shift for ten."""

    BINDINGS = [
        Binding("up", "bump(1)", "size up", show=False),
        Binding("down", "bump(-1)", "size down", show=False),
        Binding("shift+up", "bump(10)", "size up 10", show=False),
        Binding("shift+down", "bump(-10)", "size down 10", show=False),
    ]

    def action_bump(self, direction: int) -> None:
        raw = self.value.strip()
        if raw.endswith("%"):
            return  # percentages are typed, not bumped
        try:
            current = Decimal(raw) if raw else Decimal(0)
        except InvalidOperation:
            return
        # Preserve any fractional shares the user typed (e.g. 12.5 -> 13.5).
        self.value = str(max(Decimal(1), current + direction))


class OrderPanel(Vertical):
    # These shadow the market pane's same-key bindings while the panel has
    # focus, so the still-relevant ones must stay visible in the footer.
    BINDINGS = [
        Binding("escape", "close_or_back", "close order"),
        Binding("tab", "next_field", "field"),
        Binding("shift+tab", "next_field", "prev field", show=False),
        Binding("ctrl+g", "cycle_tif", "tif", show=False),
        Binding("y", "confirm_yes", "place", show=False),
        Binding("n", "confirm_no", "edit", show=False),
        Binding("b", "side('BUY')", "buy", show=False),
        Binding("s", "side('SELL')", "sell", show=False),
        Binding("space", "flip_side", "buy/sell"),
    ]

    DEFAULT_CSS = """
    OrderPanel {
        height: auto;
        border-top: solid $panel-lighten-2;
        padding: 0 1;
        display: none;
    }
    OrderPanel.open {
        display: block;
    }
    OrderPanel .field-row {
        height: 3;
    }
    OrderPanel Label {
        padding: 1 1 0 0;
        width: 6;
    }
    OrderPanel Input {
        width: 1fr;
    }
    OrderPanel #op-summary {
        height: 1;
        text-style: bold;
    }
    OrderPanel #op-info {
        height: auto;
        color: $text-muted;
    }
    OrderPanel #op-issues {
        height: auto;
    }
    OrderPanel #op-confirm {
        height: auto;
        display: none;
    }
    OrderPanel.confirming #op-confirm {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._market: Market | None = None
        self._side: Side = Side.BUY
        self._outcome_index = 0
        self._tif: Tif = Tif.GTC
        self._confirming: OrderDraft | None = None
        self._position_size: float | None = None  # shares held of the selected token

    def compose(self):
        yield Static(id="op-summary")
        with Horizontal(classes="field-row"):
            yield Label("price")
            # Disabled while closed: hidden-but-focusable inputs would steal
            # the screen's autofocus and swallow the b/s keys.
            yield PriceInput(placeholder="cents (empty = market)", id="op-price", disabled=True)
            yield Label("size")
            yield SizeInput(placeholder="qty or %", id="op-size", disabled=True)
        yield Static(id="op-info")
        yield Static(id="op-issues")
        yield Static(id="op-confirm")

    # -- open / close -----------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.has_class("open")

    def open(self, market: Market, side: Side, outcome_index: int, book: OrderBook | None) -> None:
        self._market = market
        self._side = side
        self._outcome_index = outcome_index
        self._set_confirming(None)
        self.add_class("open")
        for field in ("#op-price", "#op-size"):
            self.query_one(field, Input).disabled = False
        price_input = self.query_one("#op-price", PriceInput)
        if book is not None and book.midpoint is not None and not price_input.value:
            price_input.value = f"{round_to_tick(market, Decimal(str(book.midpoint))) * 100:.1f}"
        self.query_one("#op-issues", Static).update("")
        # Price first: confirm or adjust what you pay before how much.
        self.query_one("#op-price", PriceInput).focus()
        self._load_position_size()
        self._refresh_summary()

    def close(self) -> None:
        self.remove_class("open")
        self._set_confirming(None)
        for field in ("#op-price", "#op-size"):
            widget = self.query_one(field, Input)
            widget.value = ""
            widget.disabled = True
        # Return focus to the market pane's outcome table. Clearing focus (as
        # before) is fine when the pane is a Screen, but MarketPane is a widget
        # whose key bindings only fire while it (or a child) holds focus.
        pane = self._market_pane()
        if pane is not None:
            pane.focus_inner()
        else:
            self.screen.set_focus(None)

    def set_side(self, side: Side) -> None:
        if side is self._side:
            return
        self._side = side
        self._set_confirming(None)
        self._refresh_summary()

    def set_outcome(self, outcome_index: int) -> None:
        if self._outcome_index != outcome_index:
            self._outcome_index = outcome_index
            self._set_confirming(None)
            # Old price belonged to the other outcome's book.
            self.query_one("#op-price", PriceInput).value = ""
            self._load_position_size()
            self._refresh_summary()

    @work(exclusive=True, group="op-position")
    async def _load_position_size(self) -> None:
        """Cache shares held of the selected token so '50%' sells can resolve."""
        self._position_size = None
        market = self._market
        if market is None or not self.app.settings.can_read_portfolio:
            return
        token = market.token_id(self._outcome_index)
        if token is None:
            return
        try:
            await self.app.portfolio.positions()
        except Exception:
            return
        pos = self.app.portfolio.position_for(token)
        self._position_size = pos.size if pos else 0.0
        self._refresh_summary()

    # -- draft ------------------------------------------------------------------

    def _market_pane(self):
        """The MarketPane that owns this order panel and the live book.

        Resolved by walking ancestors for the `is_market_pane` marker rather
        than self.screen (which is the NavHost when the pane is hosted in the
        drill split) and rather than importing MarketPane (import cycle)."""
        node = self.parent
        while node is not None:
            if getattr(node, "is_market_pane", False):
                return node
            node = node.parent
        return None

    def _screen_book(self) -> OrderBook | None:
        return getattr(self._market_pane(), "_book", None)

    def _current_draft(self) -> tuple[OrderDraft | None, str]:
        market = self._market
        if market is None:
            return None, "no market"
        token_id = market.token_id(self._outcome_index)
        if token_id is None:
            return None, "no token for this outcome"
        outcomes = market.outcomes or ["Yes", "No"]
        outcome_label = outcomes[self._outcome_index]

        raw_price = self.query_one("#op-price", PriceInput).value.strip()
        book = self._screen_book()
        if not raw_price:
            # Market order: marketable limit at the touch, FAK.
            if book is None:
                return None, "book still loading"
            touch = book.best_ask if self._side is Side.BUY else book.best_bid
            if touch is None:
                return None, "book empty on that side"
            price = Decimal(str(touch.price))
            is_market = True
            tif = Tif.FAK
        else:
            parsed = parse_price(raw_price)
            if parsed is None:
                return None, "price in cents? (e.g. 33.4, or empty for market)"
            price = parsed
            is_market = False
            tif = self._tif

        raw_size = self.query_one("#op-size", Input).value.strip()
        if raw_size.endswith("%"):
            if self._position_size is None:
                return None, "position unknown - cannot size by %"
            try:
                pct = Decimal(raw_size[:-1])
            except InvalidOperation:
                return None, "size %?"
            # Keep fractional precision: 100% must fully close a fractional position.
            size = Decimal(str(self._position_size)) * pct / 100
        else:
            try:
                size = Decimal(raw_size)
            except InvalidOperation:
                return None, "size?"

        return (
            OrderDraft(
                market=market,
                token_id=token_id,
                outcome_label=outcome_label,
                side=self._side,
                price=price,
                size=size,
                tif=tif,
                is_market_order=is_market,
            ),
            "",
        )

    # -- rendering ----------------------------------------------------------------

    @property
    def _outcome_style(self) -> str:
        # Yes/No carry the strong color; index 0 = Yes side of the pair.
        return "bold green" if self._outcome_index == 0 else "bold red"

    @property
    def _side_style(self) -> str:
        # Side is muted so the outcome color reads first.
        return "dim green" if self._side is Side.BUY else "dim red"

    def _refresh_summary(self) -> None:
        summary = self.query_one("#op-summary", Static)
        info = self.query_one("#op-info", Static)
        draft, error = self._current_draft()
        out = Text()
        out.append(f"{self._side.value} ", style=self._side_style)
        if draft is None:
            outcomes = (self._market.outcomes if self._market else None) or ["Yes", "No"]
            out.append(f"{outcomes[self._outcome_index]}  ", style=self._outcome_style)
            out.append(error, style="dim")
            summary.update(out)
            hint = Text(
                "enter: next/review  esc: close  up/down: step (shift x10)  b/s/space: side",
                style="dim",
            )
            if self._side is Side.SELL and self._position_size:
                hint.append(
                    f"   held {self._position_size:,.0f} - size 50% sells half", style="yellow"
                )
            info.update(hint)
            return
        kind = "MARKET" if draft.is_market_order else f"limit {draft.tif.value}"
        out.append(f"{draft.size:,.0f} ", style="bold")
        out.append(f"{draft.outcome_label.upper()} ", style=self._outcome_style)
        out.append(f"@ {draft.price * 100:.1f}c ", style="bold cyan")
        out.append(f"({kind})", style="dim")
        summary.update(out)

        detail = Text()
        if draft.side is Side.BUY:
            detail.append(f"cost {fmt.money(float(draft.notional))}")
            detail.append(
                f" -> pays {fmt.money(float(draft.size))} if {draft.outcome_label.upper()}",
                style="green",
            )
        else:
            detail.append(f"proceeds {fmt.money(float(draft.notional))}")
        book = self._screen_book()
        if book and book.midpoint is not None:
            detail.append(f"   mid {fmt.cents(book.midpoint)}", style="dim")
        mode = self.app.settings.mode
        detail.append(f"   [{mode.value}]", style="yellow" if mode is Mode.TRADER_DRY else "red")
        info.update(detail)

    def _set_confirming(self, draft: OrderDraft | None) -> None:
        self._confirming = draft
        confirm = self.query_one("#op-confirm", Static) if self.is_mounted else None
        if draft is None:
            self.remove_class("confirming")
            self.can_focus = False
            if confirm is not None:
                confirm.update("")
            return
        self.add_class("confirming")
        self.can_focus = True  # so the y/n/esc bindings receive keys
        live = self.app.settings.mode is Mode.TRADER_LIVE
        out = Text()
        out.append(
            " PLACE " if live else " DRY-RUN ",
            style="bold reverse red" if live else "bold reverse yellow",
        )
        out.append(f" {draft.side.value} ", style=self._side_style)
        out.append(f"{draft.size:,.0f} ", style="bold")
        out.append(f"{draft.outcome_label.upper()} ", style=self._outcome_style)
        kind = "MARKET" if draft.is_market_order else f"limit {draft.tif.value}"
        out.append(f"@ {draft.price * 100:.1f}c ({kind})  ", style="bold cyan")
        out.append("y", style="bold reverse")
        out.append(" place  ")
        out.append("esc", style="bold reverse")
        out.append(" edit")
        if confirm is not None:
            confirm.update(out)
        self.focus()  # move focus off the inputs so y/esc hit panel bindings

    # -- events --------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        self._set_confirming(None)
        self._refresh_summary()

    def on__side_switching_input_close_requested(self, event) -> None:
        self.close()

    def on_side_key(self, event: SideKey) -> None:
        if event.side is None:
            self.set_side(Side.SELL if self._side is Side.BUY else Side.BUY)
        else:
            self.set_side(event.side)

    def action_side(self, side: str) -> None:
        self.set_side(Side(side))

    def action_flip_side(self) -> None:
        self.set_side(Side.SELL if self._side is Side.BUY else Side.BUY)

    def on_price_input_bumped(self, event: PriceInput.Bumped) -> None:
        self.bump_price(event.direction)

    def bump_price(self, direction: int) -> None:
        if self._market is None:
            return
        price_input = self.query_one("#op-price", PriceInput)
        current = parse_price(price_input.value)
        book = self._screen_book()
        if current is None:
            if book is None or book.midpoint is None:
                return
            current = round_to_tick(self._market, Decimal(str(book.midpoint)))
        tick = tick_size(self._market)
        bumped = max(tick, min(Decimal("1") - tick, current + tick * direction))
        price_input.value = f"{bumped * 100:.1f}"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "op-price":
            self.query_one("#op-size", Input).focus()
            return
        self.run_review()

    # -- review & place ---------------------------------------------------------------

    def _input_signature(self) -> tuple:
        """Snapshot of everything a draft depends on, to detect edits mid-review."""
        return (
            self.query_one("#op-price", Input).value.strip(),
            self.query_one("#op-size", Input).value.strip(),
            self._side,
            self._tif,
        )

    @work(exclusive=True, group="op-review")
    async def run_review(self) -> None:
        issues_widget = self.query_one("#op-issues", Static)
        draft, error = self._current_draft()
        if draft is None:
            issues_widget.update(Text(error, style="red"))
            return
        signature = self._input_signature()
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

        # Guard against edits during the awaits above: if the price/size/side/tif
        # changed, or the panel closed, do not arm a confirmation on the stale
        # draft - the user must press enter again to review the current values.
        if not self.is_open or self._input_signature() != signature:
            self._set_confirming(None)
            return

        issues = app.orders.validate(draft, self._screen_book(), cash, position)
        blocks = [i for i in issues if i.level is IssueLevel.BLOCK]
        warns = [i for i in issues if i.level is IssueLevel.WARN]
        report = Text()
        for issue in blocks:
            report.append(f"x {issue.message}\n", style="red")
        for issue in warns:
            report.append(f"! {issue.message}\n", style="yellow")
        issues_widget.update(report)
        if blocks:
            self._set_confirming(None)
            return
        self._set_confirming(draft)

    def action_confirm_yes(self) -> None:
        if self._confirming is None:
            return
        draft = self._confirming
        app = self.app
        pane = self._market_pane()  # the market pane, for a post-fill position refresh
        self._set_confirming(None)

        async def _place_and_report() -> None:
            result = await app.orders.place(draft)
            if result.ok and result.dry_run:
                app.notify(f"DRY RUN: {draft.summary()} signed, not posted", timeout=6)
            elif result.ok:
                app.portfolio.invalidate()
                app.refresh_account_status()
                # Refresh the market pane's YOUR POSITION strip so the fill shows
                # without leaving and re-entering it.
                if getattr(pane, "is_mounted", False) and hasattr(pane, "load_position"):
                    pane.load_position()
                app.notify(f"Order {result.status or 'submitted'}: {draft.summary()}", timeout=6)
            elif result.status_unknown:
                # The post may have landed; never auto-retry. Offer to reconcile.
                target = ReconcileTarget.from_draft(draft)
                body = Text()
                body.append(result.error + "\n\n", style="yellow")
                body.append(f"{draft.summary()}\n\n")
                body.append(
                    "The order may have been placed. Check Open Orders before re-placing.",
                    style="dim",
                )

                def _reconcile(confirmed: bool | None) -> None:
                    if confirmed:
                        app.open_reconciliation(target)

                app.push_screen(
                    ConfirmModal("ORDER STATUS UNKNOWN", body, "check open orders"), _reconcile
                )
            else:
                app.notify(result.error, severity="error", timeout=10)

        # App-lifetime worker: closing the panel must not cancel an in-flight post.
        app.run_worker(_place_and_report(), group="place-order", exclusive=False)
        self.close()

    def action_confirm_no(self) -> None:
        if self._confirming is not None:
            self._set_confirming(None)
            self.query_one("#op-size", Input).focus()

    def action_close_or_back(self) -> None:
        if self._confirming is not None:
            self.action_confirm_no()
        else:
            self.close()

    def action_next_field(self) -> None:
        price = self.query_one("#op-price", PriceInput)
        size = self.query_one("#op-size", Input)
        (size if price.has_focus else price).focus()

    def action_cycle_tif(self) -> None:
        self._tif = TIF_CYCLE[(TIF_CYCLE.index(self._tif) + 1) % len(TIF_CYCLE)]
        self._set_confirming(None)
        self._refresh_summary()
