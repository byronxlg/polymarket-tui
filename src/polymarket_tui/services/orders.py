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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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

    @property
    def notional(self) -> Decimal:
        return self.price * self.size

    def summary(self) -> str:
        kind = "MARKET" if self.is_market_order else f"LIMIT {self.tif}"
        return (
            f"{self.side} {format_shares(self.size)} {self.outcome_label.upper()}"
            f" @ {format_price_cents(self.market, self.price)} ({kind})"
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


def _tick(market: Market) -> Decimal:
    return Decimal(str(market.order_price_min_tick_size or 0.01))


def tick_size(market: Market) -> Decimal:
    return _tick(market)


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


def round_to_tick(market: Market, price: Decimal) -> Decimal:
    tick = _tick(market)
    return (price / tick).quantize(Decimal(1), rounding=ROUND_HALF_UP) * tick


def price_decimals(market: Market) -> int:
    """Decimal places a CENTS price can carry at this market's tick.

    Cents resolution is the tick scaled to cents: 0.01$ tick -> 1c steps ->
    0 places; 0.001$ -> 0.1c -> 1 place; 0.0001$ -> 0.01c -> 2 places.
    """
    exponent = (_tick(market) * 100).normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def format_price_cents(market: Market, price: Decimal) -> str:
    """A dollar price as cents at the market's tick resolution (min 1 place).

    What the user confirms must be exactly what is signed: fmt.cents' fixed
    .1f would show 33.45c as 33.4c on a 0.01c-tick market.
    """
    return f"{price * 100:.{max(1, price_decimals(market))}f}c"


def format_shares(size: Decimal) -> str:
    """Shares for display: whole when whole, any fraction kept (12.5 sells
    from a '50%' entry must not confirm as '12')."""
    text = f"{size:,.2f}".rstrip("0").rstrip(".")
    return text or "0"


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

        # 2. tick size
        tick = _tick(market)
        if (draft.price % tick) != 0:
            nearest = round_to_tick(market, draft.price)
            issues.append(
                Issue(
                    IssueLevel.BLOCK,
                    f"Price must be a multiple of {tick} - nearest valid"
                    f" {format_price_cents(market, nearest)}.",
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
                issues.append(
                    Issue(IssueLevel.BLOCK, f"Selling {draft.size:,.0f} but you hold {held:,.0f}.")
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
