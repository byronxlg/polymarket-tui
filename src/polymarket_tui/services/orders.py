"""Order drafting, validation, and placement.

Every order passes the same pipeline (trading.md): no fast path. Dry-run is the
default - orders are signed but not posted unless POLYMARKET_EXECUTION_LIVE=1.
All money math uses Decimal; floats only at the client boundary.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from pathlib import Path

from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.core.config import BUILDER_CODE, Mode, Settings
from polymarket_tui.models.market import Market, OrderBook
from polymarket_tui.state.watchlist import DATA_DIR

AUDIT_PATH = Path(DATA_DIR) / "orders.jsonl"
DUPLICATE_WINDOW_S = 10.0


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Tif(StrEnum):
    GTC = "GTC"
    FOK = "FOK"
    FAK = "FAK"


class IssueLevel(StrEnum):
    WARN = "warn"
    BLOCK = "block"


@dataclass
class Issue:
    level: IssueLevel
    message: str


@dataclass
class OrderDraft:
    market: Market
    token_id: str
    outcome_label: str
    side: Side
    price: Decimal  # dollars, 0-1
    size: Decimal  # shares
    tif: Tif = Tif.GTC
    is_market_order: bool = False  # marketable limit + FAK
    # The exchange's tick when this draft was built, off the live book. Carried
    # on the draft so every surface that echoes the price back - the confirm
    # strip, the summary, the audit line - reads it at the resolution it will be
    # signed at, even if the tick moves between drafting and confirming.
    tick: Decimal | None = None

    @property
    def notional(self) -> Decimal:
        return self.price * self.size

    def price_label(self) -> str:
        """The price exactly as it will be signed (min 1 place, per trading.md)."""
        decimals = decimals_for_tick(self.tick) if self.tick else price_decimals(self.market)
        return f"{self.price * 100:.{max(1, decimals)}f}c"

    def summary(self) -> str:
        kind = "MARKET" if self.is_market_order else f"LIMIT {self.tif}"
        return (
            f"{self.side} {format_shares(self.size)} {self.outcome_label.upper()}"
            f" @ {self.price_label()} ({kind})"
        )


@dataclass
class PlaceResult:
    ok: bool
    dry_run: bool
    status: str = ""
    order_id: str = ""
    error: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def status_unknown(self) -> bool:
        """A live post that raised (e.g. timeout): may have landed, never retried."""
        return not self.ok and not self.dry_run and "status unknown" in self.error.lower()


def _tick(market: Market, book: OrderBook | None = None) -> Decimal:
    """The exchange's current tick for this market.

    The CLOB is the only authority. It stamps tick_size on every book snapshot
    (REST and ws) and announces changes with `tick_size_change` as a price nears
    0 or 1. Gamma's orderPriceMinTickSize mirrors it, but a pane snapshots its
    Market once and the home list can serve one a day old from disk cache - so
    it is the fallback for the window before the first book lands, never the
    answer once we have a book. Pass the book wherever one is in hand.

    The fallback rounds *up* to the coarser 0.01. That direction is deliberate:
    an over-coarse tick makes us render 33c for 33.4c, which is visibly wrong,
    where an over-fine one would silently offer prices the exchange rejects.
    """
    if book is not None and book.tick_size:
        return book.tick_size
    return Decimal(str(market.order_price_min_tick_size or 0.01))


def tick_size(market: Market, book: OrderBook | None = None) -> Decimal:
    return _tick(market, book)


def parse_price(raw: str) -> Decimal | None:
    """Parse a price entry in CENTS: '33.4' = 33.4c, '1' = 1c, '0.1' = 0.1c.

    Always cents - matching every price the UI displays. Returns dollars
    (0-1 scale) or None if unparseable.
    """
    raw = raw.strip().lower().rstrip("c").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value / 100


def round_to_tick(market: Market, price: Decimal, book: OrderBook | None = None) -> Decimal:
    tick = _tick(market, book)
    return (price / tick).quantize(Decimal(1), rounding=ROUND_HALF_UP) * tick


def decimals_for_tick(tick: Decimal) -> int:
    """Decimal places a CENTS price can carry at `tick`.

    Cents resolution is the tick scaled to cents: 0.01$ tick -> 1c steps ->
    0 places; 0.001$ -> 0.1c -> 1 place; 0.0001$ -> 0.01c -> 2 places.
    Ticks need not be powers of ten: World Cup markets trade on 0.0025 -> 2.
    """
    exponent = (tick * 100).normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def price_decimals(market: Market, book: OrderBook | None = None) -> int:
    """Decimal places a CENTS price can carry at this market's tick."""
    return decimals_for_tick(_tick(market, book))


def format_price_cents(market: Market, price: Decimal, book: OrderBook | None = None) -> str:
    """A dollar price as cents at the market's tick resolution (min 1 place).

    What the user confirms must be exactly what is signed: fmt.cents' fixed
    .1f would show 33.45c as 33.4c on a 0.01c-tick market.
    """
    return f"{price * 100:.{max(1, price_decimals(market, book))}f}c"


def normalize_shares(size: Decimal) -> Decimal:
    """Drop trailing zeros without ever dropping a significant digit."""
    q = size.normalize()
    if q != q.to_integral_value():
        return q
    # normalize() turns 10 into 1E+1; put whole numbers back into plain form.
    # A size past the Decimal context's precision cannot be quantized - no real
    # book has one, but a formatter must not raise on the money path.
    with localcontext() as ctx:
        ctx.traps[InvalidOperation] = False
        plain = q.quantize(Decimal(1))
    return q if plain.is_nan() else plain


def format_shares(size: Decimal) -> str:
    """Shares for display: whole when whole, every fraction digit kept.

    The price_label rule applies to size too - what the user confirms must be
    exactly what is signed. A `.2f` here rounded a 28.3393-share cash-out to
    "28.34", which is not only the wrong number on the card but *more than the
    position*, so the inventory guard hard-blocked the app's own prefill with
    "Selling 28 but you hold 28."
    """
    return f"{normalize_shares(size):,f}" or "0"


def format_cents_input(raw: str, decimals: int) -> str:
    """Reformat a partially-typed CENTS price as the user types.

    The first two digits are whole cents and the decimal point is inserted
    automatically before the third digit, so "334" -> "33.4" (every valid
    Polymarket price is < 100c, so two whole-cent digits always suffice). An
    explicitly typed "." is honoured, so sub-cent entries like "5.5" still
    work. Fractional length is capped to `decimals` (the market's cent
    resolution); at 0 the price is whole cents only. Empty in, empty out.
    """
    if not raw:
        return ""
    had_dot = "." in raw
    if had_dot:
        before, _, after = raw.partition(".")
        int_digits = [c for c in before if c.isdigit()][:2]
        frac_digits = [c for c in after if c.isdigit()][:decimals]
    else:
        digits = [c for c in raw if c.isdigit()]
        if not digits:
            return ""
        int_digits = digits[:2]
        frac_digits = digits[2 : 2 + decimals] if decimals else []
    int_part = str(int("".join(int_digits))) if int_digits else ""
    frac_part = "".join(frac_digits)
    if frac_part or (had_dot and decimals):
        return f"{int_part}.{frac_part}"
    return int_part


@dataclass(frozen=True)
class FillSplit:
    """How much of a draft crosses the live book right now, and what becomes of
    the rest. Derived locally from the book we already stream - never from the
    post response, whose makingAmount/takingAmount orientation the CLOB does
    not document (docs/api-reference.md). An estimate by nature: the book moves
    between drafting and matching, so every surface renders it with a '~'.
    """

    fills: Decimal  # shares that cross at this limit price
    rests: Decimal  # shares left over (resting for GTC, cancelled for FAK)

    @property
    def total(self) -> Decimal:
        return self.fills + self.rests

    @property
    def fills_all(self) -> bool:
        return self.rests <= 0 and self.fills > 0

    @property
    def fills_none(self) -> bool:
        return self.fills <= 0


def fill_split(draft: OrderDraft, book: OrderBook | None) -> FillSplit | None:
    """Shares of `draft` that the resting book would fill immediately.

    A SELL crosses every bid priced at or above its limit; a BUY crosses every
    ask priced at or below it. Summing that depth answers the question the
    order panel could never answer before: does this fill now, or does it sit
    on the book? A GTC sell at the best bid - the cash-out prefill - fills only
    as deep as that bid, and quietly rests the remainder.

    FOK is all-or-nothing, so a book that cannot fill the whole size fills none
    of it. Returns None when there is no book to reason about (the caller then
    says nothing rather than guessing).
    """
    if book is None:
        return None
    if draft.side is Side.SELL:
        levels = [lvl for lvl in book.bids if Decimal(str(lvl.price)) >= draft.price]
    else:
        levels = [lvl for lvl in book.asks if Decimal(str(lvl.price)) <= draft.price]
    depth = sum((Decimal(str(lvl.size)) for lvl in levels), Decimal(0))
    fills = min(draft.size, depth)
    if draft.tif is Tif.FOK and fills < draft.size:
        fills = Decimal(0)  # fill-or-kill: partial depth fills nothing
    return FillSplit(fills=fills, rests=draft.size - fills)


def fill_split_label(draft: OrderDraft, split: FillSplit) -> str:
    """One plain-English line: what happens the instant this order is signed.

    The leftover's fate is the TIF's, so it is named rather than implied - a
    resting remainder is the thing users miss, and a cancelled one must never
    read as a fill. Sizes carry '~' because the book moves under us.
    """
    # A market order is a FAK marketable limit at the touch; both kill the rest.
    kills = draft.is_market_order or draft.tif in (Tif.FAK, Tif.FOK)
    if split.fills_none:
        if draft.tif is Tif.FOK:
            return "nothing fills now - too little depth, the order is killed"
        if kills:
            return "nothing fills now - the order is cancelled, not rested"
        return "nothing fills now - it rests on the book"
    if split.fills_all:
        return f"fills all ~{format_shares(split.fills)} now"
    leftover = format_shares(split.rests)
    fate = "cancelled" if kills else "rests on the book"
    return f"fills ~{format_shares(split.fills)} now, ~{leftover} {fate}"


def placement_label(draft: OrderDraft, result: PlaceResult) -> str:
    """Plain-English outcome of a live post, asserting only what `status` proves.

    The CLOB documents `live` (resting on the book) and `matched` (crossed a
    resting order) but not makingAmount/takingAmount, so a `matched` GTC that
    only partly crossed cannot be given a fill size from the response alone.
    The exact split arrives on /ws/user as size_matched; this line is the
    fallback for when that socket is down, so it points at the open-orders tab
    instead of inventing a number. Never say "Filled: SELL 100" when 40 filled.
    """
    order = (
        f"{draft.side.value} {format_shares(draft.size)} "
        f"{draft.outcome_label.upper()} @ {draft.price_label()}"
    )
    status = (result.status or "").lower()
    if status == "live":
        return f"Resting on the book: {order} - nothing filled"
    if status == "matched":
        # A market/FAK/FOK remainder is killed; a GTC remainder rests silently.
        kills = draft.is_market_order or draft.tif in (Tif.FAK, Tif.FOK)
        tail = "any remainder was cancelled" if kills else "check open orders for any remainder"
        return f"Matched: {order} - {tail}"
    return f"Order {result.status or 'submitted'}: {order}"


# Known CLOB rejection strings -> user-facing messages (trading.md).
ERROR_MAP = [
    ("not enough balance", "Insufficient USDC balance/allowance."),
    ("invalid tick size", "Price is not a multiple of this market's tick."),
    ("minimum size", "Below this market's minimum order size."),
    ("order_version_mismatch", "Internal signing bug (V1 order) - report this."),
]


def map_error(error_msg: str) -> str:
    for fragment, message in ERROR_MAP:
        if fragment in error_msg.lower():
            return message
    return error_msg or "Order rejected (no reason given)."


class OrderService:
    def __init__(self, settings: Settings, authed: AuthedClobClient | None) -> None:
        self._settings = settings
        self._authed = authed
        self._recent: list[tuple[float, str]] = []  # (monotonic, fingerprint)

    # -- validation --------------------------------------------------------------

    def validate(
        self,
        draft: OrderDraft,
        book: OrderBook | None,
        cash_balance: float | None,
        position_size: float | None,
    ) -> list[Issue]:
        issues: list[Issue] = []
        market = draft.market

        # 1. market open. Gamma's acceptingOrders is the exchange's own gate;
        # a past endDate is NOT one - markets awaiting resolution trade past it.
        if not market.active or market.closed:
            issues.append(Issue(IssueLevel.BLOCK, "Market is closed."))
        if not market.accepting_orders:
            issues.append(Issue(IssueLevel.BLOCK, "Market is not accepting orders."))

        # 4. price bounds (checked before tick so the message is clearer)
        if not Decimal("0") < draft.price < Decimal("1"):
            issues.append(Issue(IssueLevel.BLOCK, "Price must be between 0c and 100c."))
            return issues

        # 2. tick size. The live book's tick, not Gamma's snapshot: blocking a
        # 33.4c order as "not a multiple of 0.01" on a market the exchange has
        # already re-gridded to 0.001 is exactly the paternalism trading.md bans.
        tick = _tick(market, book)
        if (draft.price % tick) != 0:
            nearest = round_to_tick(market, draft.price, book)
            issues.append(
                Issue(
                    IssueLevel.BLOCK,
                    f"Price must be a multiple of {tick} - nearest valid"
                    f" {format_price_cents(market, nearest, book)}.",
                )
            )

        # 3. min size (a non-positive size reports only the positivity block)
        min_size = Decimal(str(market.order_min_size or 5))
        if draft.size <= 0:
            issues.append(Issue(IssueLevel.BLOCK, "Size must be positive."))
        elif draft.size < min_size:
            issues.append(Issue(IssueLevel.BLOCK, f"Minimum {min_size:,.0f} shares."))

        # 5. funds / inventory
        if draft.side is Side.BUY and cash_balance is not None:
            if draft.notional > Decimal(str(cash_balance)):
                issues.append(
                    Issue(
                        IssueLevel.BLOCK,
                        f"Costs ${draft.notional:,.2f} but cash is ${cash_balance:,.2f}.",
                    )
                )
        if draft.side is Side.SELL and position_size is not None:
            # Unknown holdings (positions failed to load) must not hard-block a
            # sell the exchange would accept - mirror the BUY cash guard above.
            held = Decimal(str(position_size))
            if draft.size > held:
                # Both sizes at full precision: rounding them to whole shares
                # rendered a 28.34-vs-28.3393 overshoot as "Selling 28 but you
                # hold 28.", which reads as a bug in the app rather than a
                # number the user can act on.
                issues.append(
                    Issue(
                        IssueLevel.BLOCK,
                        f"Selling {format_shares(draft.size)} but you hold {format_shares(held)}.",
                    )
                )

        # Blocks above mirror exchange rejections only - an order failing them
        # cannot succeed. Everything below is advisory: warnings, never blocks,
        # and only for rare likely-mistake situations.

        # far off mid: probably a typo'd price
        mid = Decimal(str(book.midpoint)) if book and book.midpoint is not None else None
        if mid is not None and mid > 0 and not draft.is_market_order:
            deviation = abs(draft.price - mid) / mid
            if deviation > Decimal("0.10"):
                issues.append(
                    Issue(
                        IssueLevel.WARN,
                        f"Price is {deviation:.0%} off mid ({mid * 100:.1f}c).",
                    )
                )

        # unusually large order for this account's configured comfort level
        if draft.notional > Decimal(str(self._settings.pmtui_max_notional)):
            issues.append(
                Issue(
                    IssueLevel.WARN,
                    f"Notional ${draft.notional:,.2f} exceeds PMTUI_MAX_NOTIONAL"
                    f" (${self._settings.pmtui_max_notional:,.0f}).",
                )
            )

        # accidental double-submit
        fingerprint = f"{draft.token_id}|{draft.side}|{draft.price}|{draft.size}"
        now = time.monotonic()
        self._recent = [(t, f) for t, f in self._recent if now - t < DUPLICATE_WINDOW_S]
        if any(f == fingerprint for _, f in self._recent):
            issues.append(Issue(IssueLevel.WARN, "Identical order placed seconds ago."))

        return issues

    # -- placement ----------------------------------------------------------------

    async def place(self, draft: OrderDraft) -> PlaceResult:
        if self._authed is None:
            return PlaceResult(ok=False, dry_run=False, error="Not authenticated.")

        from py_clob_client_v2 import OrderArgs, OrderType

        # Always stamp the hardcoded Builders-Program code (config.BUILDER_CODE) so
        # every order - including those placed by other people running the TUI - is
        # attributed to us. Not configurable by design.
        order_args = OrderArgs(
            token_id=draft.token_id,
            price=float(draft.price),
            size=float(draft.size),
            side=draft.side.value,
            builder_code=BUILDER_CODE,
        )
        order_type = OrderType.FAK if draft.is_market_order else getattr(OrderType, draft.tif.value)
        live = self._settings.mode is Mode.TRADER_LIVE

        if not live:
            # Dry run: sign (proves the whole signing path) but never post. Nothing
            # is placed, so do not seed the duplicate-order fingerprint.
            try:
                await self._authed.sign_order(order_args)
            except Exception as exc:
                result = PlaceResult(ok=False, dry_run=True, error=f"signing failed: {exc}")
                self._audit(draft, result)
                return result
            result = PlaceResult(ok=True, dry_run=True, status="dry-run (signed, not posted)")
            self._audit(draft, result)
            return result

        # Record the attempt only now: a live post may land (even on timeout), so
        # a subsequent identical order within the window is worth warning about.
        fingerprint = f"{draft.token_id}|{draft.side}|{draft.price}|{draft.size}"
        self._recent.append((time.monotonic(), fingerprint))

        try:
            resp = await self._authed.create_and_post_order(order_args, order_type)
        except Exception as exc:
            # A timed-out post may still have placed the order - never auto-retry.
            result = PlaceResult(
                ok=False,
                dry_run=False,
                error=f"Order status unknown ({exc}) - check Open Orders before retrying.",
            )
            self._audit(draft, result)
            return result

        success = bool(resp.get("success"))
        result = PlaceResult(
            ok=success,
            dry_run=False,
            status=str(resp.get("status", "")),
            order_id=str(resp.get("orderID", "")),
            error="" if success else map_error(str(resp.get("errorMsg", ""))),
            raw=resp,
        )
        self._audit(draft, result)
        return result

    # -- cancel -----------------------------------------------------------------

    async def cancel(self, order_id: str) -> PlaceResult:
        """Cancel one order. Gated by the same live switch as placement and audited.

        The CLOB cancel endpoint reports declines inside a 200 response
        (canceled / not_canceled maps) - a non-exception response is not success.
        """
        if self._authed is None:
            return PlaceResult(ok=False, dry_run=False, error="Not authenticated.")

        live = self._settings.mode is Mode.TRADER_LIVE
        if not live:
            result = PlaceResult(
                ok=True, dry_run=True, order_id=order_id, status="dry-run (cancel not posted)"
            )
            self._audit_cancel(order_id, result)
            return result

        try:
            resp = await self._authed.cancel_order(order_id)
        except Exception as exc:
            result = PlaceResult(
                ok=False,
                dry_run=False,
                order_id=order_id,
                error=f"Cancel status unknown ({exc}) - check Open Orders.",
            )
            self._audit_cancel(order_id, result)
            return result

        canceled = [str(o) for o in (resp.get("canceled") or [])]
        not_canceled = resp.get("not_canceled") or {}
        if order_id in canceled:
            result = PlaceResult(
                ok=True, dry_run=False, order_id=order_id, status="canceled", raw=resp
            )
        else:
            reason = str(not_canceled.get(order_id, "exchange declined the cancel"))
            result = PlaceResult(ok=False, dry_run=False, order_id=order_id, error=reason, raw=resp)
        self._audit_cancel(order_id, result)
        return result

    def _audit_cancel(self, order_id: str, result: PlaceResult) -> None:
        try:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "action": "cancel",
                            "order_id": order_id,
                            "dry_run": result.dry_run,
                            "ok": result.ok,
                            "status": result.status,
                            "error": result.error,
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass

    # -- audit ---------------------------------------------------------------------

    def _audit(self, draft: OrderDraft, result: PlaceResult) -> None:
        try:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "market": draft.market.slug,
                            "token_id": draft.token_id,
                            "outcome": draft.outcome_label,
                            "side": draft.side.value,
                            "price": str(draft.price),
                            "size": str(draft.size),
                            "tif": draft.tif.value,
                            "market_order": draft.is_market_order,
                            "dry_run": result.dry_run,
                            "ok": result.ok,
                            "status": result.status,
                            "order_id": result.order_id,
                            "error": result.error,
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass
