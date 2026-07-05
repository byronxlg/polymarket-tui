# User journeys

The product is graded against two personas. Every journey below is scripted
in `journeys/` and runs through the real app against live APIs
(`scripts/tui_journey.py`); review the step PNGs like a user, not like a
diff (docs/evaluation.md).

## Personas

**Casual (Sam)** browses for interesting markets, buys or sells small
amounts, checks how their bets are doing. Sam will not learn hotkeys:
everything must be reachable with arrows / Enter / Escape plus whatever the
footer visibly offers on that screen. On-screen prompts must carry the
whole flow; a step that requires remembering an invisible key fails.

**Expert (Alex)** already knows the market they want, holds positions and
resting orders, and wants the minimum keystrokes between intent and
action. Hotkeys are fine but must be few, mnemonic, and shown in the
footer where they matter; chords and vim-isms are out (design principle:
a small core, one meaning each).

Grading: each journey gets pass / friction / fail per iteration.
- **pass** - completes as scripted, every needed key visible or obvious,
  no dead ends, screens readable.
- **friction** - completes but with avoidable steps, hidden keys a casual
  would need, misleading footer, or layout problems.
- **fail** - cannot complete, crashes, or silently does the wrong thing.

## Casual journeys

| id | journey | script |
|----|---------|--------|
| C1 | Discover: boot -> scroll trending -> open event -> open outcome -> read prices/chart -> back out to home | `c1_discover.json` |
| C2 | Browse a category: home -> up to category bar -> across -> pick one -> browse its list | `c2_category.json` |
| C3 | First buy: market page -> footer "buy" -> panel defaults -> size -> review -> confirm (DRY) -> understand result | `c3_first_buy.json` |
| C4 | Research before buying: rules, chart timeframe, recent trades, comments on event + market | `c4_research.json` |
| C5 | Track interests: star from a list (space) -> find the watchlist again later | `c5_watch.json` |
| C6 | Check my money: portfolio -> balances, positions, P&L readable at a glance | `c6_portfolio.json` |
| C7 | Sell what I own: portfolio -> position -> Enter -> market -> sell -> size -> review (DRY) | `c7_sell.json` |
| C8 | Search a topic: "/" -> type words -> pick a result -> open it | `c8_search.json` |
| C9 | Mistake recovery: dive deep, then Escape all the way home; quit safely | `c9_recovery.json` |

## Expert journeys

| id | journey | script |
|----|---------|--------|
| E1 | Straight to a known market: "/" -> query -> Enter -> market page (count keystrokes) | `e1_direct.json` |
| E2 | Quick order from a list row: home/watchlist row -> b -> armed panel without drilling | `e2_quick_order.json` |
| E3 | Book ladder: market -> into book -> cursor levels -> quick order at a level | `e3_book_ladder.json` |
| E4 | Cancel a resting order: p -> tab to orders -> x -> y; also x from a book level | `e4_cancel.json` |
| E5 | Limit order shaping: outcome flip (y/n), price ticks, size, review - all from the keyboard | `e5_limit.json` |
| E6 | Watchlist as workspace: w -> row -> quick order; space unstars | `e6_watchlist.json` |
| E7 | Position to market: p -> position -> Enter -> market with book, then back into portfolio | `e7_pos_to_market.json` |
| E8 | Trader intel: "/" -> tab to traders -> open profile -> follow (space) | `e8_trader.json` |
| E9 | Mode control: L toggles DRY/LIVE with explicit confirm; header states the mode | `e9_mode.json` (manual-only; never confirmed LIVE in automation) |

## Test environments

Journeys never run against the real `$HOME`: the credentials file persists
Byron's LIVE flag, and an automated keypress must never be able to place a
real order.

- **anon** - empty temp HOME; app boots signed out. For browse / search /
  research journeys.
- **authed-dry** - temp HOME with `credentials.toml` copied from the real
  one and `execution_live` forced to `false`. For portfolio, order-panel,
  and cancel journeys; posts stay dry-run.

`scripts/journey_env.sh <anon|authed-dry>` prints a prepared HOME path;
journey JSONs reference it via their `command` field.

## Iteration log

### Iteration 1 (2026-07-05, 8305f5b)

Pass: C1, C2, C4, C6, C8, C9, E1, E2, E4, E6, E7. Failures and friction,
all fixed on this branch:

| finding | grade | fix |
|---------|-------|-----|
| F7 trader search crashed the app: null entries in the search payload failed Profile validation, and the error toast itself died in Textual's markup parser | E8 fail | gamma.search skips non-dict entries; app.notify renders literally (markup=False) by default |
| F5 sell from a position you own opened SELL on the outcome under the cursor (YES) instead of the owned outcome (NO) | C7 fail | action_order(SELL) retargets to the owned outcome before opening the panel |
| F2 order panel asked "size?" while focusing the prefilled price field - typed digits replaced the price (5c instead of 96.7c) | C3 fail | focus follows the open question: size gets focus whenever price is prefilled |
| F3 price/size inputs accepted any character; stray y/n confirm keys landed as text | C3/E5 friction | restrict= on both inputs (digits, dot, % for size) |
| F1 home footer hid enter/open while the list was focused | C1 friction | visible enter binding on EventsTable, event MarketsTable, PositionsTable |
| F4 watchlist unreachable for casuals: w hidden, star toast said nothing | C5 friction | toast says "w opens your watchlist"; w visible in the home footer |
| F6 "ends ended" phrasing on ended markets | C7 nit | title says just "ended" |
| F8 order-book ws badge said LIVE in green - collides with LIVE = real money | C1 nit | badge reads "streaming" |
| F9 duplicate x-axis tick labels on short-range charts | C7 nit | consecutive duplicate labels dropped |

### Iteration 2 (2026-07-05)

Re-ran C1, C3, C5, C7, E3, E5, E8 against the fixes; E5 rescripted for the
size-first focus (Tab reaches price for tick stepping). All seven pass:

- C3: space -> "5" lands in size -> enter arms "DRY-RUN BUY 5 YES @ 96.4c".
- C5: star toast says "w opens your watchlist"; home footer shows
  "enter open ... w watched".
- C7: sell from a 40-No position opens SELL No on the No book with a
  "Selling your No position" toast and the "held 40 - 50% sells half" hint;
  title reads "ended".
- E3: space on a book level pre-fills the level price, focus on size.
- E5: full keyboard limit flow places DRY; a stray y during edit is
  rejected by the input instead of corrupting the size.
- E8: trader search opens profiles; no crash on malformed profile entries.
- Book badge reads "streaming"; chart tick labels no longer repeat.

Remaining grade: casual journeys C1-C9 pass; expert journeys E1-E8 pass
(E9 stays manual-only by design).
