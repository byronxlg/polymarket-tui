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
| E8 | Trader intel: "/" -> tab to traders -> down into list -> follow (space) -> open profile | `e8_trader.json` |
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

### Iteration 3 (2026-07-05) - navigation consistency sweep

Walked every drill/back/overlay path in the real app (anon + authed-dry)
and mapped actual vs expected screens. Three inconsistencies found, all
fixed on this branch:

| finding | grade | fix |
|---------|-------|-----|
| F10 'e' on a market drilled from its own event nested a duplicate event pane (Home > WCW > France > WCW); the trail grew unboundedly | E-nav fail | NavHost.drill reuses the parent pane when its drill_key matches - focus steps back instead of nesting |
| F11 escape died on Home-as-parent: HomePane bound esc to leave_tag_bar, so the split could never be collapsed with esc (left worked) - C9-style recovery stalled one level from home | C9 friction | esc -> app.nav_back like every pane; the tag-bar step-out moved into HomePane.handle_back |
| F12 "press space on a trader" (watchlist empty note, help) was impossible: search pinned focus in the input, so space typed text; stars/follows were mouse-only | E8 fail | down flows focus into the result list (up at top / left / esc return to the input); space stars/follows there and the footer advertises it only while the list is focused |

Re-ran C2, C8, C9 (extended with esc5_full_home), E8 (extended with
follow_from_list): all pass. Verified untouched paths still behave:
watchlist/portfolio root swaps, order panel open/edit/review/close, cancel
strips, chart inspect, book focus flow, overlays (search/help/auth), tag
bar, H, `<`, quick-order warnings.

### Iteration 4 (2026-07-06) - enter confirms everywhere; confirm surfaces restyled

Confirm keys unified (Byron's request): enter proceeds and esc steps back
on every confirm surface - the order strip (was y), both cancel strips
(was y), and ConfirmModal (already enter). Every surface ignores keys for
the 0.15s arming beat, so a queued or held enter cannot confirm while a
deliberate confirm still lands on the first press; verified by sending a
rapid double-enter (reviews, does not place) and a deliberate enter (places
DRY).

Visual pass on the same surfaces: op-confirm and the cancel strips get a
severity-tinted full-width row (amber DRY / red LIVE-or-cancel) and shared
reverse-chip key hints; ConfirmModal drops the thick blue brick border for
a round tone-colored one (danger red for LIVE/clear-creds, amber for the
status-unknown prompt) with a chip title.

Re-run: C3 and E5 pass with the new keys (E5's edit_back rescripted to
esc). E4 could not be re-driven - the account held no resting orders at
run time - but the cancel path shares the arming/strip code verified via
C3 and a widget-level render.

### Iteration 5 (2026-07-06) - order entry moved top right; leaner order flow

The order panel moved from under the book into the top of the trades rail
(Byron: "move the buy screen to top right") - the full-height book stays
visible while ordering. Read-before-enter cut down: the armed state hides
the summary/info lines it used to repeat and shows chip / order / keys on
three short lines; the edit-state hint shrank to "up/down step - space
side - enter review" (esc/tab live in the footer); the cost line drops the
mid (the book is adjacent) and the "L = go live" aside. Warnings stay
visible while armed.

Re-run C3, C7, E5: all pass with the panel top right; C3/E5 place DRY.

### Iteration 6 (2026-07-06) - calmer confirm styling

Byron flagged the armed LIVE strip as ugly and scary: a murky red wash,
a reversed salmon "PLACE" chip that read as an un-clickable button, and
heavy reversed key chips. All confirm surfaces now use a quiet callout -
thick left accent bar (amber DRY / red LIVE and cancels), no background
wash, the mode stated plainly ("LIVE - posts for real" / "DRY-RUN -
signs, never posts" / "CANCEL"), and footer-style key hints (bold key,
dim label). The order panel's boxed 3-row inputs became borderless
one-row fields (focus = lighter field; an explicit :focus border-none
keeps the default tall focus border from swallowing the single row).
ConfirmModal titles are plain bold in the tone color.

Re-run C3: passes; DRY places with enter. LIVE and cancel callouts
verified widget-level (no resting orders / never go live in automation).

### Iteration 7 (2026-07-06) - fixed-height P&L charts; teardown crash fixed

The portfolio profit chart was height 1fr (absorb-the-rest), so it
rendered huge over empty tables and shrank when rows loaded (Byron). Both
P&L strips (portfolio, trader profile) are now fixed strips like the
market chart: height 30% / min 10 (25% at the medium tier); the tables
own the space above and scroll internally. Verified: the chart title row
is identical while loading, after load, and across tabs.

Stress-testing the fix exposed a crash family: swapping the drill root
(H/p/w) or tearing down drill panes while loaders were mid-fetch let
worker tails and call_after_refresh callbacks touch dismantled panes -
NoMatches panics on Home, Portfolio (twice) and Event panes. Removal is
async, so is_mounted alone leaves a window where the pane is mounted but
its children are pruned. Fix: NavHost._discard stamps the pane and all
descendants _nav_discarded synchronously and cancels their workers before
removing; every loader tail and _refit checks ui.liveness.alive(). 27
rounds of rapid root-swap + drill churn now run crash-free (previously
crashed within 5).

### Iteration 8 (2026-07-06) - buy/sell visible in compact activity

Byron: "User activity does not show buy vs sell." At full and medium
widths the Side column exists, but the compact activity tier (portfolio
History / trader History as the 30% drill parent, or any narrow fit)
dropped it - a trade feed reading "$20.00" with no direction. The compact
tier now carries a 1-wide colored B/S letter column (the trades-rail
idiom); wider tiers keep the full word.
