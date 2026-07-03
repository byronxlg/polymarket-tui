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
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path

from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.core.config import Mode, Settings
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
            f"{self.side} {self.size:,.0f} {self.outcome_label.upper()}"
            f" @ {self.price * 100:.1f}c ({kind})"
        )


@dataclass
class PlaceResult:
    ok: bool
    dry_run: bool
    status: str = ""
    order_id: str = ""
    error: str = ""
    raw: dict = field(default_factory=dict)


def _tick(market: Market) -> Decimal:
    return Decimal(str(market.order_price_min_tick_size or 0.01))


def round_to_tick(market: Market, price: Decimal) -> Decimal:
    tick = _tick(market)
    return (price / tick).quantize(Decimal(1), rounding=ROUND_HALF_UP) * tick


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

        # 1. market open
        if not market.active or market.closed:
            issues.append(Issue(IssueLevel.BLOCK, "Market is closed."))
        if market.end_date is not None and market.end_date < datetime.now(UTC):
            issues.append(Issue(IssueLevel.BLOCK, "Market has ended."))

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
                    f"Price must be a multiple of {tick} - nearest valid {nearest * 100:.1f}c.",
                )
            )

        # 3. min size
        min_size = Decimal(str(market.order_min_size or 5))
        if draft.size < min_size:
            issues.append(Issue(IssueLevel.BLOCK, f"Minimum {min_size:,.0f} shares."))
        if draft.size <= 0:
            issues.append(Issue(IssueLevel.BLOCK, "Size must be positive."))

        # 5. funds / inventory
        if draft.side is Side.BUY and cash_balance is not None:
            if draft.notional > Decimal(str(cash_balance)):
                issues.append(
                    Issue(
                        IssueLevel.BLOCK,
                        f"Costs ${draft.notional:,.2f} but cash is ${cash_balance:,.2f}.",
                    )
                )
        if draft.side is Side.SELL:
            held = Decimal(str(position_size or 0))
            if draft.size > held:
                issues.append(
                    Issue(IssueLevel.BLOCK, f"Selling {draft.size:,.0f} but you hold {held:,.0f}.")
                )

        # 6/7. price sanity vs book
        mid = Decimal(str(book.midpoint)) if book and book.midpoint is not None else None
        if mid is not None and mid > 0 and not draft.is_market_order:
            deviation = abs(draft.price - mid) / mid
            if deviation > Decimal("0.10"):
                issues.append(
                    Issue(
                        IssueLevel.BLOCK,
                        f"Price is {deviation:.0%} off mid ({mid * 100:.1f}c) - adjust it.",
                    )
                )
            elif deviation > Decimal("0.02"):
                issues.append(
                    Issue(IssueLevel.WARN, f"Price is {deviation:.1%} off mid ({mid * 100:.1f}c).")
                )
        if book is not None:
            best_ask = book.best_ask
            best_bid = book.best_bid
            if (
                draft.side is Side.BUY
                and best_ask is not None
                and draft.price >= Decimal(str(best_ask.price))
            ):
                issues.append(
                    Issue(
                        IssueLevel.WARN,
                        f"Crosses the spread - fills immediately at {best_ask.price * 100:.1f}c.",
                    )
                )
            if (
                draft.side is Side.SELL
                and best_bid is not None
                and draft.price <= Decimal(str(best_bid.price))
            ):
                issues.append(
                    Issue(
                        IssueLevel.WARN,
                        f"Crosses the spread - fills immediately at {best_bid.price * 100:.1f}c.",
                    )
                )

        # 8. fat finger
        if draft.notional > Decimal(str(self._settings.pmtui_max_notional)):
            issues.append(
                Issue(
                    IssueLevel.BLOCK,
                    f"Notional ${draft.notional:,.2f} exceeds PMTUI_MAX_NOTIONAL"
                    f" (${self._settings.pmtui_max_notional:,.0f}).",
                )
            )
        elif (
            cash_balance
            and draft.side is Side.BUY
            and draft.notional > Decimal(str(cash_balance)) * Decimal("0.25")
        ):
            issues.append(Issue(IssueLevel.WARN, "Order is more than 25% of your cash."))

        # 9. duplicate guard
        fingerprint = f"{draft.token_id}|{draft.side}|{draft.price}|{draft.size}"
        now = time.monotonic()
        self._recent = [(t, f) for t, f in self._recent if now - t < DUPLICATE_WINDOW_S]
        if any(f == fingerprint for _, f in self._recent):
            issues.append(
                Issue(IssueLevel.BLOCK, "Identical order placed seconds ago - wait or adjust.")
            )

        return issues

    # -- placement ----------------------------------------------------------------

    async def place(self, draft: OrderDraft) -> PlaceResult:
        if self._authed is None:
            return PlaceResult(ok=False, dry_run=False, error="Not authenticated.")

        from py_clob_client_v2 import OrderArgs, OrderType

        order_args = OrderArgs(
            token_id=draft.token_id,
            price=float(draft.price),
            size=float(draft.size),
            side=draft.side.value,
        )
        order_type = OrderType.FAK if draft.is_market_order else getattr(OrderType, draft.tif.value)
        live = self._settings.mode is Mode.TRADER_LIVE

        fingerprint = f"{draft.token_id}|{draft.side}|{draft.price}|{draft.size}"
        self._recent.append((time.monotonic(), fingerprint))

        if not live:
            # Dry run: sign (proves the whole signing path) but never post.
            try:
                await self._authed.sign_order(order_args)
            except Exception as exc:
                result = PlaceResult(ok=False, dry_run=True, error=f"signing failed: {exc}")
                self._audit(draft, result)
                return result
            result = PlaceResult(ok=True, dry_run=True, status="dry-run (signed, not posted)")
            self._audit(draft, result)
            return result

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
