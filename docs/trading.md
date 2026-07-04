# Trading design

The only part of the app that moves money. Correctness and explicitness beat convenience.

## Principles

1. **Every order passes the same validation pipeline** - no fast path.
2. **Every order is confirmed** with an explicit `y` keypress on an armed
   confirm strip showing exactly what will be signed.
3. **Decimal everywhere.** Prices and sizes are `decimal.Decimal` from input to
   `OrderArgs`. Floats appear nowhere in order math.
4. **Live-fire switch.** LIVE mode (auth-screen toggle with confirmation, or
   `POLYMARKET_EXECUTION_LIVE=1`) is required to actually post. Otherwise
   dry-run: the full pipeline runs and the order is signed (proving the
   EIP-712 path) but never posted. LIVE is never persisted across sessions.

## Order form

Inline panel below the live order book (b/s opens it; the book stays visible):

- Two fields only: price (cents, focused first, tick-rounded mid prefill) and
  size (shares, or a percentage of the held position when selling).
- Empty price = market order (marketable limit at the touch, FAK).
- b/s/space flip the side from anywhere in the panel; up/down bump by one
  tick/share, shift for ten; ctrl+g cycles TIF (GTC/FOK/FAK).
- A bold summary line (side muted, outcome colored, price cyan) plus
  cost/payout re-render on every keystroke.

## Validation pipeline (`services/orders.py`)

Policy: **the app never blocks an order the exchange would accept.** Hard
blocks exist only for orders that cannot succeed - they mirror exchange
rejections. Everything judgment-shaped is at most a rare yellow warning.

| Check | Source | Outcome |
|---|---|---|
| Market open (`active && !closed`, not past endDate) | Gamma | block |
| Tick size: price % `orderPriceMinTickSize` == 0 | Gamma | block, with nearest-valid suggestion |
| Min size: size >= `orderMinSize` (usually 5) | Gamma | block |
| Price in (0, 1) exclusive | - | block |
| Balance: BUY needs `cost <= usdc_balance`; SELL needs `size <= position` | CLOB / data-api | block |
| Price > 10% off midpoint (limit orders) | live book | warn |
| Notional > PMTUI_MAX_NOTIONAL | settings | warn |
| Identical order placed < 10s ago | session log | warn |

Warnings render inline in the order panel in yellow and never prevent the
confirm step; blocks list the reason and keep the panel in edit state.

## Confirm step

Enter runs the pipeline; if nothing blocks, a reverse-video strip arms in the
panel: `DRY-RUN  BUY 10 YES @ 33.4c (limit GTC)  y place  esc edit`. `y`
places (the panel becomes focusable only at this point so a queued keypress
cannot fire it); esc/left steps back to editing.

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

Fills will arrive authoritatively on the user WS channel once M2 lands;
today the open-orders tab refetches on demand.

## Cancels

`x` on an open order (portfolio, orders tab) -> confirm modal -> cancel via
`cancel_order(OrderPayload)`. Cancels obey the same live gate as placement
(DRY mode never posts a cancel), are audited to the JSONL log, and the
response's `canceled`/`not_canceled` maps are checked - a 200 response is
not success.

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
