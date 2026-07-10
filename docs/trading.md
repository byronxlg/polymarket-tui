# Trading design

The only part of the app that moves money. Correctness and explicitness beat convenience.

## Principles

1. **Every order passes the same validation pipeline** - no fast path.
2. **Every order is confirmed** with a deliberate enter on an armed
   confirm strip showing exactly what will be signed. The strip ignores
   keys for 0.15s after arming (ConfirmModal.ARM_DELAY_S), so the enter
   that reviewed cannot also place - but the beat stays below human reaction
   time, so a deliberate confirm lands on the first press.
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

### Sell prefills: `s` means cash out

`s` prefills the **whole held position at the best bid**, so `s -> enter ->
enter` cashes out. Two rules keep that promise:

- **Sizes are exact.** The prefill is the position to the last digit
  (28.3393, never a rounded 28.34). Rounding it to 2dp rounded *up* past the
  holding, and the inventory guard then hard-blocked the app's own prefill.
  `format_shares` therefore keeps every fraction digit: what is shown is what
  is signed, for size exactly as for price.
- **A parked book cursor is not a chosen price.** `b`/`s` from a focused book
  prefill the highlighted level - but only once the user has *moved* the
  cursor (`BookPanel.cursor_chosen`). The book takes focus whenever the pane
  opens, with the cursor parked on the best ask, and honouring that parked row
  armed every sell at the ask: a price that cannot cross, so the "cash out"
  rested on the book instead of filling.

## Validation pipeline (`services/orders.py`)

Policy: **the app never blocks an order the exchange would accept.** Hard
blocks exist only for orders that cannot succeed - they mirror exchange
rejections. Everything judgment-shaped is at most a rare yellow warning.

| Check | Source | Outcome |
|---|---|---|
| Market open (`active && !closed && acceptingOrders`) | Gamma | block |
| Tick size: price % tick == 0 | live book (`tick_size`), Gamma fallback | block, with nearest-valid suggestion |
| Min size: size >= `orderMinSize` (usually 5) | Gamma | block |
| Price in (0, 1) exclusive | - | block |
| Balance: BUY needs `cost <= usdc_balance`; SELL needs `size <= position` | CLOB / data-api | block |
| Price > 10% off midpoint (limit orders) | live book | warn |
| Notional > PMTUI_MAX_NOTIONAL | settings | warn |
| Identical order placed < 10s ago | session log | warn |

Warnings render inline in the order panel in yellow and never prevent the
confirm step; blocks list the reason and keep the panel in edit state.

### Where the tick comes from

The exchange re-grids a market (typically 0.01 -> 0.001) as its price nears 0
or 1, announcing it with the `tick_size_change` ws frame and stamping the
current value on every `book` frame and every REST `/book`. **That is the only
authority.** Gamma's `orderPriceMinTickSize` is a mirror, snapshotted into
`MarketPane._market` when the pane opens and never refreshed - and the home
list can hand a pane one up to 24h old from disk cache.

So `OrderBook.tick_size` wins wherever a book is in hand: `_tick(market, book)`
in services/orders.py, the book panel's own render resolution, and `OrderDraft.
tick` (carried on the draft so the confirm strip echoes the price at the
resolution it will be signed at). Gamma is the fallback for the window before
the first book lands. Reading the stale value made the app render 33.4c as 33c
and hard-block a legal 33.4c order as "not a multiple of 0.01" - which py-clob-
client, resolving the tick from the CLOB itself, would have signed happily.

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
    fills all ~10 now
    cost   $3.34
    payout $10.00 if it wins
    enter place   esc edit

(a SELL shows `proceeds $X` instead of cost/payout.) Numbers are bold, the
outcome carries the colour, and the mode word says what enter will do.

### Does it fill, or does it rest?

The line under the price answers the question the card could never answer, from
the live book (`fill_split` in services/orders.py): sum the depth the limit
price crosses - bids at or above it for a SELL, asks at or below it for a BUY.

    fills all ~28.3393 now                    (green)
    fills ~736.23 now, ~263.77 rests on the book   (amber - the surprising case)
    nothing fills now - it rests on the book   (dim - an ordinary limit order)

The leftover's fate is named, never implied: a GTC remainder **rests**, a
market/FAK/FOK remainder is **cancelled**, and a FOK that cannot fill whole
fills nothing. Sizes carry `~` because the book moves between drafting and
matching. When only part of it crosses, `cost`/`proceeds` read "if it all
fills" - they price the whole order, not the fill.

A second enter places - the panel becomes focusable only at this point and
ignores keys for the 0.15s arming beat, so a queued enter cannot fire it
while a deliberate confirm still lands on the first press; esc/left steps
back to editing.

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

Map response to UX. The post response carries `makingAmount`/`takingAmount`, but
the CLOB does **not** document which is shares and which is USDC for a given
side, so no fill size is ever derived from them. `status` is documented, and
`size_matched` on the `/ws/user` order frame is the trustworthy share count.

| Result | UX |
|---|---|
| `success && status == "matched"` | "Matched: SELL 100 YES @ 33.4c - check open orders for any remainder" (a matched GTC may have crossed only partly). A market/FAK/FOK order says "any remainder was cancelled" |
| `success && status == "live"` | "Resting on the book: ... - nothing filled" |
| `success && status in (delayed, unmatched)` | falls back to the raw status word |
| `success == False` | sticky red toast with mapped `errorMsg`; form retains values |

Those are `placement_label`, and they only fire when `/ws/user` is **down**.
While the socket is up it echoes the exact split from `size_matched`
(`order_event_label` in ui/widgets/order_details.py), and the local toast is
suppressed so one placement raises one alert:

| ws order frame | toast |
|---|---|
| `MATCHED` | `Filled: SELL 100 Yes @ 33.4c` |
| `LIVE`, `size_matched > 0` | `Partly filled: SELL 100 Yes @ 33.4c - 40 filled, 60 resting` |
| `LIVE`, `size_matched == 0` | `Resting on the book: SELL 100 Yes @ 33.4c - nothing filled` |
| `CANCELED` | `Canceled: SELL 60 Yes @ 33.4c (40 of 100 had filled)` |

The lead word answers "filled, or resting?" before the numbers land. Quoting
`original_size` here (as it once did) announced a 100-share sell that filled 40
as "Order resting: SELL 100 Yes".

After any placement: invalidate balance + positions caches; append to the session order
log (in-memory + JSONL at `~/.local/share/polymarket-tui/orders.jsonl` for audit).

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
