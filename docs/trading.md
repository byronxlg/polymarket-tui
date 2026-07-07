# Trading design

The only part of the app that moves money. Correctness and explicitness beat convenience.

## Principles

1. **Every order passes the same validation pipeline** - no fast path.
2. **Every order is confirmed** with a deliberate enter on an armed
   confirm strip showing exactly what will be signed. The strip ignores
   keys for 0.35s after arming (ConfirmModal.ARM_DELAY_S), so the enter
   that reviewed cannot also place.
3. **Decimal everywhere.** Prices and sizes are `decimal.Decimal` from input to
   `OrderArgs`. Floats appear nowhere in order math.
4. **Live-fire switch.** LIVE mode (global `L` toggle or auth-screen select,
   both confirmed via the arming modal, or `POLYMARKET_EXECUTION_LIVE=1`) is
   required to actually post. Otherwise dry-run: the full pipeline runs and
   the order is signed (proving the EIP-712 path) but never posted. The flag
   persists with the credentials; a session that starts LIVE announces it.

## Order form

Inline panel at the top of the right rail (b/s opens it; the live book
stays fully visible beside it):

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
| Market open (`active && !closed && acceptingOrders`) | Gamma | block |
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

Enter runs the pipeline; if nothing blocks, the panel arms in place. The
order panel is a bordered "ORDER" card at the top of the right rail (blue
while editing); arming promotes the whole card border to amber (DRY) / red
(LIVE). The raw price/size fields are hidden and the card restates the order
as one scannable block, ranked by what a user checks before enter - what/how
much, then the money it moves:

    DRY-RUN · signs, never posts
    BUY 10 YES
    @ 33.4c   limit GTC
    cost   $3.34
    payout $10.00 if it wins
    enter place   esc edit

(a SELL shows `proceeds $X` instead of cost/payout.) Numbers are bold, the
outcome carries the colour, and the mode word says what enter will do.

A second enter places - the panel becomes focusable only at this point and
ignores keys for the 0.35s arming beat, so a queued enter cannot fire it;
esc/left steps back to editing.

## Placement and result handling

```python
signed = client.create_order(OrderArgs(token_id, price, size, side))   # to_thread
resp   = client.post_order(signed, order_type)                          # to_thread
```

`OrderService.place` always adds `builder_code=BUILDER_CODE` to `OrderArgs` so matched
fills are attributed on-chain (Polymarket Builders Program, issue #12). Attribution is
stamped at signing time by whichever instance signs the order, so `BUILDER_CODE` is
**hardcoded** in `core/config.py`: every install attributes to us, which is the only way
to get attribution from other people running the TUI (the code must be present in the
instance that signs). The code is public (an on-chain identifier), not a secret.

There is deliberately **no** env var or config override - an override would just hand
every user a switch to redirect attribution away from us. Removing attribution requires
editing the `BUILDER_CODE` constant in source. That is friction, not enforcement: being
open source, a user editing the source can always strip it; only server-side signing could
truly enforce it. Builder fees stay at the profile default of 0 bps - the user pays no
builder cost. A non-zero fee would be a user-visible cost and must be disclosed in the
order panel first (design principle: money is never careless).

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

`x` on an open order arms an inline full-detail strip; enter confirms (same
arming beat) -> cancel via `cancel_order(OrderPayload)`. Two surfaces:

- **Market page**: `x` on a starred book level arms a red "CANCEL ORDER"
  card in the *same top-of-rail slot the order panel uses* - placing and
  cancelling happen in one place, and the book on the left stays put.
- **Portfolio, orders tab**: the same full-detail strip above the table.

Cancels obey the same live gate as placement
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
placed the order. Never auto-retry. The app states the facts in a dismiss-only modal
(status unknown, may or may not have landed, will not be retried) and leaves the user
to check Open Orders before re-placing - it does not guess whether the post landed.
