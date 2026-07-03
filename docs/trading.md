# Trading design

The only part of the app that moves money. Correctness and explicitness beat convenience.

## Principles

1. **Every order passes the same validation pipeline** - no fast path.
2. **Every order is confirmed in a modal** showing exactly what will be signed. No
   "don't ask again" option in v1.
3. **Decimal everywhere.** Prices and sizes are `decimal.Decimal` from input to
   `OrderArgs`. Floats appear nowhere in order math.
4. **Live-fire switch.** `POLYMARKET_EXECUTION_LIVE=1` required to actually post orders.
   Without it the app runs in dry-run: full pipeline, confirm modal, then logs the
   would-be order instead of posting (matches the shared-data-feeds convention).

## Order form

Fields and behavior (Market screen, bottom-right panel):

| Field | Values | Notes |
|---|---|---|
| Side | BUY / SELL | `b`/`s` shortcuts preset it |
| Outcome | YES / NO | defaults to book currently displayed |
| Type | LIMIT / MARKET | MARKET = marketable limit + FAK (no native market orders) |
| TIF | GTC / GTD / FOK / FAK | LIMIT default GTC; GTD reveals an expiry input |
| Price | decimal, in cents or dollars | disabled for MARKET (auto: best ask/bid crossed by 1 tick, shown grayed) |
| Size | shares | `m` fills max affordable (BUY) or full position (SELL) |

Live-computed display lines:

- BUY: `cost = price * size`, `to win = size * (1 - price) + cost` -> shown as
  `Cost $12.30 -> pays $100.00 if YES`
- SELL: `proceeds = price * size`
- Slippage line for MARKET: walks the book snapshot to estimate average fill price and
  worst-case price at the crossed limit.

## Validation pipeline (`services/orders.py`)

Runs on Review; each check yields pass / warn / block:

| # | Check | Source | Outcome |
|---|---|---|---|
| 1 | Market open (`active && !closed`, not past endDate) | Gamma | block |
| 2 | Tick size: price % `orderPriceMinTickSize` == 0 | Gamma (fallback: CLOB tick-size endpoint) | block, with auto-round suggestion |
| 3 | Min size: size >= `orderMinSize` (usually 5) | Gamma | block |
| 4 | Price in (0, 1) exclusive | - | block |
| 5 | Balance: BUY needs `cost <= usdc_balance`; SELL needs `size <= position size` | CLOB balance / data-api position | block |
| 6 | Price sanity: warn if limit deviates > 2% from midpoint; block > 10% unless user re-confirms with typed `yes` | live book | warn/block |
| 7 | Crossed-market awareness: BUY limit >= best ask -> "will fill immediately at ask" notice | live book | warn |
| 8 | Fat-finger notional: warn if cost > 25% of balance; typed confirm if > $500 (configurable) | - | warn |
| 9 | Duplicate guard: identical order (token, side, price, size) placed < 10s ago | session log | block |

Warnings render in the confirm modal in yellow; blocks prevent the modal opening and focus
the offending field with the reason.

## Confirm modal

```
+--------------------------------------------------------------+
|  REVIEW ORDER                              [dry-run mode]    |
|                                                              |
|  BUY 100 YES  @ 12.3c  (LIMIT, GTC)                          |
|  Will Spain win the 2026 FIFA World Cup?                     |
|                                                              |
|  Cost            $12.30                                      |
|  Payout if YES   $100.00  (+$87.70)                          |
|  Midpoint        12.25c   (deviation +0.4%)                  |
|  Balance after   $111.15                                     |
|                                                              |
|  ! will partially fill immediately: 900 available at 12.3c   |
|                                                              |
|          [ Place order (enter) ]   [ Cancel (esc) ]          |
+--------------------------------------------------------------+
```

Enter posts; esc returns to the form with values intact.

## Placement and result handling

```python
signed = client.create_order(OrderArgs(token_id, price, size, side))   # to_thread
resp   = client.post_order(signed, order_type)                          # to_thread
```

Map response to UX:

| Result | UX |
|---|---|
| `success && status == "matched"` | green toast "Filled: 100 @ 12.3c", refresh position strip |
| `success && status == "live"` | toast "Resting on book", order appears via user WS |
| `success && status in (delayed, unmatched)` | yellow toast with `errorMsg`, keep tracking via WS |
| `success == False` | sticky red toast with mapped `errorMsg`; form retains values |

After any placement: invalidate balance + positions caches; append to the session order
log (in-memory + JSONL at `~/.local/share/polymarket-tui/orders.jsonl` for audit).

Fills arrive authoritatively on the user WS channel (`trade` messages with status
MATCHED -> MINED -> CONFIRMED); the open-orders table and toasts key off those, not off
optimistic local state.

## Cancels

- Single: `x` on an open order -> small confirm (`enter` confirms) -> `client.cancel(id)`.
- All-in-market: from Market screen, `X` -> confirm listing the affected orders.
- Cancel-all: Portfolio only, requires typing `cancel all`. Never triggered by a single key.

## Error mapping

| `errorMsg` fragment | User message |
|---|---|
| `not enough balance / allowance` | "Insufficient USDC. Balance $X, needed $Y." |
| `invalid tick size` | "Price must be a multiple of {tick}. Nearest valid: {p}." |
| `minimum size` | "Minimum {n} shares for this market." |
| `order_version_mismatch` | internal bug (V1 signing) - sticky error, ask to file issue |
| network / 5xx | "Order status unknown - check Open Orders before retrying." (critical: do NOT auto-retry posts) |

The network-failure case is the dangerous one: a timed-out `post_order` may still have
placed the order. Never auto-retry; force a reconciliation read of open orders first.
