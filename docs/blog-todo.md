# Blog to-do

Topic pipeline for the blog at `site/blog/`. The daily workflow
(`.github/workflows/blog-post.yml`) is **current-events-first**: it scans
both the news (headlines with matching markets) and Polymarket itself
(trending 24h volume, sharp price moves, imminent decision dates) for the
day's story, and writes about how the event and the market relate - signals
and rules in `.claude/skills/blog-post/SKILL.md`.

The queue below is the **fallback for quiet days** with no big trend. Rules:

- Keep it ordered: most valuable next post at the top of the unchecked list.
- One line per topic: working title, then the search intent it targets.
- When a post ships, check it off and append the date and filename.
- Add new ideas at whatever position their value deserves, not just the end.

Every published post - current-events or fallback - gets a line under
Shipped; that list is how the workflow avoids re-covering an event.

## Queue (fallback)

- [ ] Limit vs market orders on Polymarket (and why market orders are really
  marketable limits) - intent: "polymarket limit order", "polymarket market order"
- [ ] Reading the trade tape: what prints tell you that the book does not -
  intent: "polymarket trade history", "order flow prediction markets"
- [ ] Dry-run trading: practice on the real exchange with nothing at stake -
  intent: "paper trading polymarket", "polymarket without money"
- [ ] Following any trader's portfolio (public wallets, read-only) - intent:
  "polymarket track trader", "polymarket whale watching"
- [ ] Charting Polymarket price history in the terminal - intent: "polymarket
  price history", "polymarket chart"
- [ ] What happens when a market resolves (redemption, UMA, disputed
  outcomes) - intent: "polymarket resolution", "how does polymarket settle"
- [ ] Ticks, minimum sizes, and other Polymarket microstructure details -
  intent: "polymarket tick size", "polymarket minimum order"
- [ ] Why a terminal client: keyboard-first trading and information density -
  intent: "polymarket cli", "terminal trading tools"
- [ ] Watchlists and staying on top of many markets at once - intent:
  "polymarket watchlist", "track multiple polymarket markets"

## Shipped

- [x] Hamas Disarmament Deal Odds on Polymarket: August 2026
  (event: Trump's US-led "Board of Peace" announced Hamas signed a Gaza
  disarmament framework in El-Alamein, Egypt, July 30, 2026 - Israel's
  government called the terms unacceptable within a day; Polymarket's
  "Will Hamas agree to disarm by December 31?" market spiked from 44c to a
  93.5c peak within the hour, then crashed to a 59.5c low over a 20-minute
  window on July 31 as the Israeli rejection landed, settling near 61.5c)
  - 2026-08-01, `site/blog/hamas-disarmament-deal-odds-august-2026.html`
- [x] NVIDIA Overtakes Apple: Polymarket's Largest-Company Odds
  (event: Apple reported Q3 FY2026 earnings after the July 30 close - revenue
  and EPS both beat estimates, but Services and Greater China revenue missed
  and guidance was weak, sending shares down 6.65% after hours from $333.43
  to $311.25; Polymarket's "Largest Company end of July?" market flipped
  within 30 minutes, NVIDIA's Yes price rising from 13.2c to 68c and Apple's
  falling from 86.75c to 31.45c, later settling near 89.4c/10.15c) -
  2026-07-31, `site/blog/nvidia-overtakes-apple-largest-company-odds.html`
- [x] Fed Holds in July 2026: What September Now Prices
  (event: the FOMC voted 9-3 to hold rates at 3.50-3.75% on July 29,
  2026 - the first split decision under Fed Chair Kevin Warsh, with
  three regional bank presidents dissenting for a hike, citing Middle
  East uncertainty and energy-driven inflation; Polymarket's July
  no-change market had drifted from 93c to a 72c low before recovering
  to resolve at 100c, and its September market now prices a 25bp hike
  as the favorite at 56.5c) - 2026-07-30,
  `site/blog/fed-holds-july-2026-september-hike-odds.html`
- [x] US-Iran Ceasefire Collapse Odds on Polymarket: July 29, 2026
  (event: IRGC launched an "attempted surprise attack" with ballistic
  missiles at a US base in Jordan on July 28, breaking the strike-pause
  covered on 2026-07-27; the US and Saudi Arabia struck Iran-backed militia
  sites in Iraq in response; Polymarket's ceasefire-by-date ladder fell
  8.5-18.5c, with the by-July-31 contract crashing from a 62.5c peak to
  34.5c within an hour then partly recovering to 41c) - 2026-07-29,
  `site/blog/us-iran-ceasefire-collapse-odds-july-2026.html`
- [x] Bitcoin Crash Odds on Polymarket: July 28, 2026
  (event: Bitcoin briefly reclaimed $65,000 on July 27 then reversed
  overnight to about $63,200 amid tightening liquidity ahead of the July
  28-29 Fed decision, spot-ETF outflows, and cascading liquidations;
  Polymarket's above-$64,000 noon-ET market fell from an 86.5c peak to 20c)
  - 2026-07-28, `site/blog/bitcoin-crash-odds-july-2026.html`
- [x] US-Iran Strike Pause Odds on Polymarket: July 2026
  (event: Trump halted the two-week-old US bombing campaign on Iran after
  July 23, following 13 consecutive nights of strikes; Iran said it would
  hold its own fire as long as the pause lasts, July 26) - 2026-07-27,
  `site/blog/us-iran-strike-pause-odds-july-2026.html`
- [x] Hungarian Grand Prix 2026 Odds: What Qualifying Moved
  (event: 2026 F1 Hungarian Grand Prix qualifying, July 25 - Norris took
  pole by 0.012s over Hamilton, then Hamilton and Antonelli were handed
  three-place grid penalties, reshuffling the Polymarket race-winner market
  ahead of the July 26 race) - 2026-07-26,
  `site/blog/hungarian-grand-prix-2026-odds-qualifying.html`
- [x] LeBron to Philadelphia 76ers: What the Signing Moved
  (event: LeBron James posted on X that he signed a two-year, $8M deal with
  the Philadelphia 76ers, July 24; the next-team market's 76ers Yes price
  jumped from 8c to 99c in five minutes, reversing the July 21-22 Miami Heat
  leak story) - 2026-07-25,
  `site/blog/lebron-to-philadelphia-76ers-signing-odds.html`
- [x] BetMoar vs polymarket-tui: choosing a Polymarket terminal
  (competitive comparison, targets "betmoar" / "polymarket terminal"
  searches; directive from Byron 2026-07-24) - 2026-07-24,
  `site/blog/betmoar-vs-polymarket-tui.html`
- [x] Israel-Iran Ceasefire Odds on Polymarket: July 2026
  (event: Iran rejected a new US-drafted truce proposal passed via Iraq as
  US strikes on Iran reached a 13th consecutive night, July 23) - 2026-07-24,
  `site/blog/israel-iran-ceasefire-odds-july-2026.html`
- [x] LeBron to Miami Heat Odds: What the Leaked Video Moved
  (event: Miami Heat social media accidentally published a "LeBron James
  Introductory Press Conference" video, July 21-22; Polymarket's Heat market
  spiked then partly faded) - 2026-07-23,
  `site/blog/lebron-to-miami-heat-odds-leaked-video.html`
- [x] Fed Rate Decision Odds on Polymarket: July 2026
  (event: Fed Decision in July market repricing toward a hike ahead of the
  July 28-29 FOMC meeting) - 2026-07-22,
  `site/blog/fed-rate-decision-july-2026-odds.html`
- [x] Ballon d'Or 2026 Odds: Kane Leads Yamal
  (event: 2026 Ballon d'Or market repricing after the World Cup final,
  July 19-21) - 2026-07-21, `site/blog/ballon-dor-2026-odds-kane-vs-yamal.html`
- [x] Why Spain vs Argentina 2026 resolved Draw on Polymarket
  (current events: World Cup final resolution, match played July 19) -
  2026-07-20, `site/blog/why-spain-vs-argentina-2026-resolved-draw.html`
- [x] Spain vs Argentina: 2026 World Cup final odds on Polymarket
  (current events: World Cup final, July 19) - 2026-07-17,
  `site/blog/spain-vs-argentina-2026-world-cup-final-odds.html`
- [x] How to read a Polymarket order book - 2026-07-17,
  `site/blog/how-to-read-a-polymarket-order-book.html`
- [x] Prices are probabilities: what a 33c share really tells you - 2026-07-17,
  `site/blog/what-a-polymarket-price-means.html`
