# Design principles

Distilled from building this app; new work should follow these unless a
better principle replaces them.

## Layout: place by decision value

Reading order (top-left first) follows what the user acts on:

1. Actionable prices - outcome tables, the order book
2. Your money - order entry, positions, balances
3. Live context - previews, rules, activity, comments
4. History - charts, demoted to strips/rails; never the hero slot

Every screen follows one shape: header (identity/balances/clock) ->
context line -> body -> footer. Detail rails sit on the right and follow
the cursor.

### Width tiers (drill panes)

Every drill pane has three variants and NavHost switches between them on
each reflow (ui/tiers.py): compact (30% parent slot - the pane is context,
only its primary list with star/title/price/24h), medium (70% child - the
main content; drop the lowest-value columns first - Ends, Spread, Avg - and
slim the rails), full (alone - the complete layout). tier-<name> classes
drive show/hide and rail sizes in app.tcss; tables rebuild their column
sets in code because DataTable columns cannot respond to CSS.

The slot tier is a cap, not the answer: a 70% pane of a small terminal is
narrower than a 30% pane of a wide one, so tables refit after layout -
effective_tier() picks the widest column set that fits the measured width
and fit_columns() shrinks the primary text column for small deficits. A
pane must never render clipped columns.

## Keys: a small core, one meaning each

- Arrows do everything first: up/down move and flow into adjacent panels
  (category bar, chart inspect, search box); right/enter drill in; left/esc
  step OUT one level (panel -> expanded view -> screen -> previous screen).
- tab / shift+tab cycle the screen's primary selector (category, timeframe,
  pane, search mode).
- space is the contextual toggle: star a list row, flip the YES/NO book,
  flip BUY/SELL in the order panel, show rules, follow a trader.
- New keybinds only when they earn their place; no aliases, no vim keys.
  Footer shows at most the few keys that matter on that screen.

## Money: never paternalistic, never careless

- The app never blocks an order the exchange would accept. Hard stops only
  mirror exchange rejections (closed market, tick, min size, bounds, funds).
  Advisory conditions are rare yellow warnings.
- Dry-run is the default; LIVE is a per-session, explicitly confirmed opt-in
  and is never persisted.
- Decimal for all order math; every order/cancel appended to the JSONL audit
  log; a timed-out post is NEVER auto-retried (it may have landed).
- Confirmation is an explicit `y` on a strip that only becomes focusable
  when armed - queued keypresses cannot place orders.

## Display conventions

- Prices in cents everywhere, including inputs ('33.4' = 33.4c). No unit
  guessing.
- Outcome carries the strong color (Yes green / No red); side (BUY/SELL) is
  muted so the outcome reads first. P&L green/red. Ended/resolved dimmed.
- Truncate with a visible ellipsis; state what flags mean in words
  ("won - redeem on web"), not jargon.

## Code shape

- One widget per concept, reused everywhere: EventsBrowser (list+preview),
  TradesTable, TraderOverview, positions-table helpers, PriceChartPanel,
  ConfirmModal. If two screens hand-roll the same table, extract it.
- Screens talk to services/clients on the app; pydantic models absorb API
  quirks (Gamma's JSON-encoded strings) at the boundary.
- Verify against the LIVE APIs before claiming done: drive the real TUI in
  tmux, probe new endpoints with curl first, pin discovered field semantics
  (sortBy, groupItemThreshold, series) in code comments.
