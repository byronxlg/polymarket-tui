"""Inline order entry, at the top of the market page's right rail.

Keyboard-first: b/s opens it preset to a side, price/size are the only two
fields (empty price = market order at the touch), up/down bump the price by
one tick, enter advances price -> size -> review, and a deliberate second
enter on the armed strip places (0.35s arming beat, so a queued enter
cannot) - the book stays visible and live the whole time.
"""

from __future__ import annotations

import time
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
    format_cents_input,
    parse_price,
    price_decimals,
    round_to_tick,
    tick_size,
)
from polymarket_tui.ui.theme import AMBER, DOWN, UP
from polymarket_tui.ui.widgets.confirm_modal import ConfirmModal
from polymarket_tui.ui.widgets.order_details import action_hints

TIF_CYCLE = [Tif.GTC, Tif.FOK, Tif.FAK]


def _fmt_size(size: Decimal) -> str:
    """Book sizes are shares - show whole shares, keep any fraction the level has."""
    text = f"{size:.2f}".rstrip("0").rstrip(".")
    return text or "0"


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
        # Fires only while confirming - in edit state the inputs own enter
        # (submit advances price -> size -> review).
        Binding("enter", "confirm_yes", "place", show=False),
        Binding("b", "side('BUY')", "buy", show=False),
        Binding("s", "side('SELL')", "sell", show=False),
        Binding("space", "flip_side", "buy/sell"),
    ]

    DEFAULT_CSS = """
    /* The order-action card: a bordered box at the top of the right rail so
       placing an order stands out against the flat navy rail (it shares this
       slot with the cancel confirm). Blue while editing; the whole border
       promotes to amber (DRY) / red (LIVE) once a place is armed, instead of
       a quieter inner left-bar. */
    OrderPanel {
        height: auto;
        display: none;
        padding: 0 1;
        margin-bottom: 1;
        border: round $primary;
        border-title-color: $primary;
        border-title-style: bold;
    }
    OrderPanel.open {
        display: block;
    }
    OrderPanel.confirming {
        border: round $warning;
        border-title-color: $warning;
    }
    OrderPanel.confirm-live {
        border: round $error;
        border-title-color: $error;
    }
    OrderPanel .field-row {
        height: 1;
        margin: 1 0;
    }
    OrderPanel Label {
        padding: 0 1 0 0;
        width: 6;
    }
    /* Borderless one-row fields: the boxed 3-row inputs read heavy in the
       rail. Focus shows as the lighter field plus the cursor block. */
    OrderPanel Input {
        width: 1fr;
        border: none;
        height: 1;
        padding: 0 1;
        background: $panel;
    }
    OrderPanel Input:focus {
        border: none;  /* the default tall focus border swallows a 1-row field */
        background: $panel-lighten-2;
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
    /* Armed confirm content (the DRY-RUN/LIVE chip, the order line, the key
       hints). No inner bar - the card's own border already carries the
       amber/red state colour. */
    OrderPanel #op-confirm {
        height: auto;
        display: none;
    }
    OrderPanel.confirming #op-confirm {
        display: block;
    }
    OrderPanel.confirming #op-summary,
    OrderPanel.confirming #op-info {
        display: none;
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
        self._position_won = False  # held token is resolved-won (redeemable)

    def compose(self):
        yield Static(id="op-summary")
        with Horizontal(classes="field-row"):
            yield Label("price")
            # Disabled while closed: hidden-but-focusable inputs would steal
            # the screen's autofocus and swallow the b/s keys.
            # restrict: stray letters (a queued y/n, a fat-fingered key) must
            # not land in the numeric fields as text.
            yield PriceInput(
                # Just "cents": "(empty = market)" clipped mid-word in the
                # narrow rail field, and the summary line already flips to
                # MARKET live when the price is left empty.
                placeholder="cents",
                id="op-price",
                disabled=True,
                restrict=r"[0-9.]*",
            )
            yield Label("size")
            yield SizeInput(
                placeholder="qty or %", id="op-size", disabled=True, restrict=r"[0-9.]*%?"
            )
        yield Static(id="op-info")
        yield Static(id="op-issues")
        yield Static(id="op-confirm")

    # -- open / close -----------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.has_class("open")

    def open(
        self,
        market: Market,
        side: Side,
        outcome_index: int,
        book: OrderBook | None,
        preset_price: Decimal | None = None,
        preset_size: Decimal | None = None,
    ) -> None:
        self._market = market
        self._side = side
        self._outcome_index = outcome_index
        self._set_confirming(None)
        self.border_title = "ORDER"
        self.add_class("open")
        for field in ("#op-price", "#op-size"):
            self.query_one(field, Input).disabled = False
        price_input = self.query_one("#op-price", PriceInput)
        size_input = self.query_one("#op-size", SizeInput)
        # Prefilled from a book level (space on the order book): both fields are
        # the level's price and size, ready to review or tweak.
        if preset_price is not None:
            price_input.value = self._fmt_price(preset_price)
        elif book is not None and book.midpoint is not None and not price_input.value:
            price_input.value = self._fmt_price(round_to_tick(market, Decimal(str(book.midpoint))))
        if preset_size is not None:
            size_input.value = _fmt_size(preset_size)
        self.query_one("#op-issues", Static).update("")
        # Focus follows the open question: whenever a price is already filled
        # in (book level, midpoint default), the panel is asking "size?" - so
        # typed digits must land in size, not silently replace the price.
        (size_input if price_input.value else price_input).focus()
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
        self._position_won = False
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
        # Won-and-resolved: selling takes the bid, redeeming on the web pays
        # the full dollar - say so (advisory only, never a block).
        self._position_won = bool(pos and pos.redeemable and pos.cur_price >= 0.5)
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

    def _price_decimals(self) -> int:
        """Cents decimal places this market's tick allows (1 if not set yet)."""
        return price_decimals(self._market) if self._market else 1

    def _fmt_price(self, dollars: Decimal) -> str:
        """A tick-aligned dollar price as a cents string at market resolution."""
        return f"{dollars * 100:.{self._price_decimals()}f}"

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
        return f"bold {UP}" if self._outcome_index == 0 else f"bold {DOWN}"

    @property
    def _side_style(self) -> str:
        # Side is muted so the outcome color reads first.
        return "dim green" if self._side is Side.BUY else f"dim {DOWN}"

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
            hint = Text("up/down step \u00b7 space side \u00b7 enter review", style="dim")
            if (
                self._side is Side.SELL
                and self._position_size
                and not self.app.settings.polymarket_hide_balances
            ):
                hint.append(
                    f"   held {self._position_size:,.0f} - size 50% sells half", style=AMBER
                )
            if self._side is Side.SELL and self._position_won:
                hint.append(
                    "\nwon - redeems at 100c on the web; selling here takes the bid",
                    style=AMBER,
                )
            info.update(hint)
            return
        kind = "MARKET" if draft.is_market_order else f"limit {draft.tif.value}"
        out.append(f"{draft.size:,.0f} ", style="bold")
        out.append(f"{draft.outcome_label.upper()} ", style=self._outcome_style)
        out.append(f"@ {draft.price * 100:.1f}c ", style="bold")
        out.append(f"({kind})", style="dim")
        summary.update(out)

        detail = Text()
        if draft.side is Side.BUY:
            detail.append(f"cost {fmt.money(float(draft.notional))}")
            detail.append(
                f" -> pays {fmt.money(float(draft.size))} if {draft.outcome_label.upper()}",
                style=UP,
            )
        else:
            detail.append(f"proceeds {fmt.money(float(draft.notional))}")
        # The live book sits right next to the panel (mid is visible there)
        # and going-live guidance lives in help - the cost line stays short.
        mode = self.app.settings.mode
        detail.append(f"   [{mode.value}]", style=AMBER if mode is Mode.TRADER_DRY else DOWN)
        info.update(detail)

    def _set_confirming(self, draft: OrderDraft | None) -> None:
        self._confirming = draft
        confirm = self.query_one("#op-confirm", Static) if self.is_mounted else None
        live = self.app.settings.mode is Mode.TRADER_LIVE
        if draft is None:
            self.remove_class("confirming", "confirm-live")
            self.can_focus = False
            if confirm is not None:
                confirm.update("")
            return
        self.add_class("confirming")
        self.set_class(live, "confirm-live")  # red tint when this posts for real
        self.can_focus = True  # so the enter/esc bindings receive keys
        # Same arming delay as ConfirmModal: an enter queued from the fields
        # (double-enter on size) must not place the order it just reviewed.
        self._confirm_armed_at = time.monotonic() + ConfirmModal.ARM_DELAY_S
        # One element per line - the strip lives in the narrow right rail and
        # must not wrap mid-token: chip, then the order, then the keys.
        out = Text()
        # The mode word, plain bold - a reversed "PLACE" chip read as a
        # scary un-clickable button; LIVE/DRY-RUN says what enter will do.
        if live:
            out.append("LIVE", style=f"bold {DOWN}")
            out.append(" - posts for real", style="dim")
        else:
            out.append("DRY-RUN", style=f"bold {AMBER}")
            out.append(" - signs, never posts", style="dim")
        out.append("\n")
        out.append(f"{draft.side.value} ", style=self._side_style)
        out.append(f"{draft.size:,.0f} ", style="bold")
        out.append(f"{draft.outcome_label.upper()} ", style=self._outcome_style)
        kind = "MARKET" if draft.is_market_order else f"limit {draft.tif.value}"
        out.append(f"@ {draft.price * 100:.1f}c ({kind})", style="bold")
        out.append("\n")
        out.append_text(action_hints(("enter", "place"), ("esc", "edit")))
        if confirm is not None:
            confirm.update(out)
        self.focus()  # move focus off the inputs so enter/esc hit panel bindings

    # -- events --------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "op-price":
            # Auto-place the decimal (334 -> 33.4) and cap to the market's tick
            # resolution as the user types. Re-assigning value re-posts Changed;
            # it re-enters with the canonical string, which formats to itself, so
            # there is no loop.
            formatted = format_cents_input(event.value, self._price_decimals())
            if formatted != event.value:
                event.input.value = formatted
                event.input.cursor_position = len(formatted)
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
        price_input.value = self._fmt_price(bumped)

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
            issues_widget.update(Text(error, style=DOWN))
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
            report.append(f"x {issue.message}\n", style=DOWN)
        for issue in warns:
            report.append(f"! {issue.message}\n", style=AMBER)
        issues_widget.update(report)
        if blocks:
            self._set_confirming(None)
            return
        self._set_confirming(draft)

    def action_confirm_yes(self) -> None:
        if self._confirming is None:
            return
        if time.monotonic() < getattr(self, "_confirm_armed_at", 0.0):
            return  # queued enter from the review keypress - not a decision
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
                # Refresh the market pane's YOUR POSITION strip and book
                # stars; positions re-poll with backoff because data-api
                # indexes fills late. Also covers a down /ws/user socket.
                if getattr(pane, "is_mounted", False) and hasattr(pane, "refresh_after_fill"):
                    pane.refresh_after_fill()
                app.notify(f"Order {result.status or 'submitted'}: {draft.summary()}", timeout=6)
            elif result.status_unknown:
                # The post may have landed; never auto-retry. Offer to reconcile.
                target = ReconcileTarget.from_draft(draft)
                body = Text()
                body.append(result.error + "\n\n", style=AMBER)
                body.append(f"{draft.summary()}\n\n")
                body.append(
                    "The order may have been placed. Check Open Orders before re-placing.",
                    style="dim",
                )

                def _reconcile(confirmed: bool | None) -> None:
                    if confirmed:
                        app.open_reconciliation(target)

                app.push_screen(
                    ConfirmModal("ORDER STATUS UNKNOWN", body, "check open orders", tone="warn"),
                    _reconcile,
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
