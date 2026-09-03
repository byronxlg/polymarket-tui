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

- [x] Charting Polymarket price history in the terminal - intent: "polymarket
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

- [x] GTA VI Extended Look Views Odds on Polymarket: September 2026 (event:
  Rockstar posted "Grand Theft Auto VI: An Extended Look" to its YouTube
  channel August 27, 2026 at 6:00pm PT (01:00 UTC August 28); Polymarket's
  twelve-bracket ladder on the video's first-168-hour YouTube view count
  drifted in a choppy 15-45c range for three days, then flipped fast around
  16:20 UTC Tuesday, September 2 - "under 20 million views" fell from 53.5c
  to 26.5c in ten minutes while "20 to 22 million" jumped from 44.5c to 72c,
  no news event behind it, just the running view-count pace on the counter
  crossing the bracket boundary early; by 2026-09-03 11:27 UTC the actual
  YouTube counter read 20,341,522 views, "under 20 million" had collapsed
  to 0.55c (-61.5pts on the day) and "20 to 22 million" priced 90.5c
  (+52pts), with "22 to 24 million" still holding a live 9.1c tail (+8.5pts)
  as the market's 23:59 UTC close approached) - 2026-09-03,
  `site/blog/gta-vi-extended-look-views-odds-polymarket-september-2026.html`
- [x] Iran Strikes Jordan and UAE Odds on Polymarket: August 2026 (event: US
  forces struck two IRGC rocket launchers on Larak Island in the Strait of
  Hormuz on Sunday, August 30, 2026 - CENTCOM said the Guard had been
  observed preparing to launch rockets with sea mines into the strait, the
  first US military action there in a month; the IRGC acknowledged
  casualties and vowed retaliation, then early Monday, August 31, launched
  ballistic missiles at Jordan's King Hussein and Al-Azraq air bases
  (Jordan says it intercepted all eight, no damage) and drones at the
  UAE's Al Minhad Air Base (UAE denies any hit, calls it "baseless");
  Polymarket's "Will Iran target an Arab country by...?" ladder, flat in a
  4-9c band all weekend, jumped to 67c within 15 minutes once reports of
  the retaliation broke at 19:30 UTC Aug 30, reached 99.5c by 02:15 UTC
  Aug 31, and formally resolved 100/0 across its August 31, September 15,
  and September 30 rungs by 14:07 UTC Aug 31 - while the broader "Israel x
  Iran ceasefire continues through...?" ladder, which only counts direct
  Israel-Iran strikes, slid a modest 6-7 points on its September-December
  legs, and "Will the US invade Iran before 2027?" moved just +3 points on
  the day) - 2026-08-31,
  `site/blog/iran-strikes-jordan-uae-odds-polymarket-august-2026.html`
- [x] Jannik Sinner Out of the 2026 US Open: Odds Move (event: world No. 1
  Jannik Sinner, unbeaten in majors he'd entered all year and 44-3 with six
  titles in 2026 including the season's first five ATP Masters 1000 events,
  withdrew from the 2026 US Open on Friday, August 21, 2026, citing a right
  knee injury dating to his Wimbledon win in July - his first missed Grand
  Slam since his 2019 major debut, and confirmed after he'd already
  withdrawn from the Montreal and Cincinnati warm-up events; Polymarket's
  "2026 Men's US Open Winner" market had already drifted Sinner's contract
  from 50.5c on August 17 to a 32-35.5c band by the morning of August 21 on
  the warm-up withdrawals, then crashed it from 35.5c to 0.15c within six
  hours (12:00-18:00 UTC) once the US Open withdrawal was official, settling
  0.05c and flipping Gamma's `closed` flag to true more than a week before
  the tournament's first match; Carlos Alcaraz absorbed the largest single
  jump (25.5c to 33c the same window) and remained the new favorite at 25.5c
  by August 30, while Alexander Zverev nearly doubled (11.25c to 21.65c) and
  kept climbing to 23.05c, closing to within 2.45c of Alcaraz as the main
  draw began) - 2026-08-30,
  `site/blog/jannik-sinner-2026-us-open-withdrawal-odds.html`
- [x] Lake America Odds on Polymarket: August 2026 (event: President Trump
  signed an executive order Thursday, August 27, 2026, renaming Lake
  Ontario "Lake America," tasking Interior Secretary Doug Burgum and the
  Board on Geographic Names with updating the Geographic Names Information
  System (GNIS) within 30 days, amid an escalating US-Canada trade war;
  Canadian PM Mark Carney rejected the rename the same day; Polymarket's
  "Google Maps renames Lake Ontario to Lake America by...?" ladder saw its
  December 31 contract jump from a 17.5c pre-news level to 94.5c within
  about four hours starting 17:15 UTC August 27 as the order landed, while
  a newly-listed "by August 31" contract - asking whether the rename would
  land within 4 days of signing, evoking the ~3-week Gulf of Mexico-to-Gulf
  of America precedent from January 2025 - launched Aug 28 at 45c, crashed
  to a 4c low within two hours, round-tripped as high as 55c twice more,
  and settled 23.7c (-26.7pts on the day) by the time of writing, two days
  before its own resolution) - 2026-08-29,
  `site/blog/lake-america-odds-polymarket-august-2026.html`
- [x] Fed Rate Hike Odds on Polymarket: Jackson Hole 2026 (event: Fed Chair
  Kevin Warsh delivered his first Jackson Hole speech as chairman at 10am ET
  (14:00 UTC) August 28, 2026, at the Kansas City Fed's annual economic
  symposium, saying "we must be confident that underlying inflation is
  moving to our objective, clearly and at sufficient speed - otherwise, we
  have work to do" with PCE inflation at 3.7% YoY (core 3.3%), while also
  rejecting explicit forward guidance as a "hall-of-mirrors problem";
  Polymarket's "Fed Decision in September?" market moved within ten minutes
  of the speech starting - "No change" fell from 69.5c to a 46.5-47.5c
  low before settling 49.5c (-18pt on the day), "25 bps increase" rose from
  30.5c to a 52.5c high before settling 49.5c (+19pt), a coin flip that had
  been a clear "no change" favorite the day before, while "25 bps decrease"
  - the favorite as recently as early August - collapsed further to 0.65c)
  - 2026-08-28, `site/blog/fed-rate-hike-odds-jackson-hole-2026.html`
- [x] Strait of Hormuz Reopening Odds on Polymarket: September 2026 (event: the
  Trump administration launched "Operation Economic Outcast" on Monday, August
  24, 2026 - Treasury Secretary Scott Bessent added five more sanctioned
  sectors (aviation, digital assets, gold, shipping, technology) to Iran's
  economy, blacklisted 60+ Iran-linked targets, and threatened secondary
  sanctions on any country still trading with Iran - yet Polymarket's Iran
  de-escalation odds barely moved on the sanctions news itself; the real
  move came the next day, Tuesday August 25, when Oman's foreign minister
  Badr Albusaidi met Iranian counterpart Abbas Araghchi in Tehran to discuss
  a "phased framework" for a temporary Strait of Hormuz shipping corridor
  and mine-clearing project, with Albusaidi calling an announcement possible
  "soon"; Polymarket's "US announces end of Iranian blockade by September
  30?" jumped from a 28.5c low to a 43c intraday peak starting 08:30 UTC
  Aug 25, settling 40.5c (every date on the blockade-end ladder closed
  green, Aug 31 through Dec 31), "Strait of Hormuz traffic returns to
  normal by September 30?" roughly doubled from 5.5c to 11.5c, and the
  "US ceasefire against Iran continues through...?" ladder also rose
  7-10 points across its September and October dates) - 2026-08-26,
  `site/blog/strait-of-hormuz-reopening-odds-september-2026.html`
- [x] How Polymarket Resolved Bitcoin's $80,000 Contract (event: Polymarket's
  "Will Bitcoin reach $80,000 in August?" contract closed at 15:43:42 UTC on
  August 24, 2026, after a single one-minute Binance BTC/USDT candle printed
  a high at or above $80,000, the culmination of the round trip this blog
  covered August 20-23 - the contract bottomed at a 42.25c low August 23
  before bitcoin's rally, fueled by continued Treasury buyback optimism and
  fresh ETF inflows, carried it to resolution, while several mainstream
  price trackers reading composite/Coinbase feeds were still describing
  bitcoin in the high $70,000s well into the next morning; post explains
  Polymarket's Gamma resolution lifecycle (closed/closedTime/acceptingOrders/
  outcomePrices freezing to ["1","0"]/umaResolutionStatus) and in-app
  redemption (won positions flagged "won - redeem on web", `o` opens
  polymarket.com), with the still-live $82,500/$85,000 rungs - up 34 and 21
  points on the day to 72.5c/42.5c - as ongoing context) - 2026-08-25,
  `site/blog/how-polymarket-resolved-bitcoins-80000-contract.html`
- [x] How to Chart Polymarket Price History in the Terminal (fallback/evergreen:
  the CLOB `/prices-history` endpoint behind polymarket-tui's chart - six
  interval tabs, a single flippable outcome on a market page vs. up to six
  outcomes overlaid on an event page, and the `x`-key crosshair for stepping
  through a series - worked with a live example from Polymarket's "Fed
  Decision in September?" event, whose No Change and Increase 25bps
  contracts moved as near mirror images over Aug 10-24, 2026: No Change from
  63.5c to a 74.5c peak on Aug 15-17 then back to 67.5c, Increase 25bps from
  34.5c to a 24.5c low then back to 31.5c) - 2026-08-24,
  `site/blog/how-to-chart-polymarket-price-history-in-the-terminal.html`
- [x] Bitcoin $80,000 Odds on Polymarket: August 2026 (event: bitcoin gained
  nearly 30% over five days to touch an intraday high near $79,500 early
  Saturday, August 22, 2026 - riding the same Treasury bond-buyback/SEC
  crypto-framework rally this blog covered August 20 plus Trump's August 19
  CLARITY Act push - then flash-crashed shortly after 04:00 UTC that same
  morning, briefly sliding under $77,000 and liquidating $523 million in a
  single hour (86% long positions) and $1.8 billion over 24 hours across
  286,130 traders, after the 4-hour RSI hit its highest reading in over
  seven years; Polymarket's "What price will Bitcoin hit in August?" ladder
  fully resolved its $75,000 and $77,500 contracts to 100c on the spike,
  while the still-contested rungs above them gave back much of Friday's
  gain by the morning of August 23 - $80,000 from a 91.4c peak to 45.35c
  (-19.6pts on the day), $82,500 from 62.5c to 25.25c (-12.9pts), $85,000 to
  12.55c (-8.2pts) - even as the order book showed real bid size (17,000+
  shares at both $80,000 and $82,500) resting just under the market rather
  than a panic-driven book) - 2026-08-23,
  `site/blog/bitcoin-80000-odds-polymarket-august-2026.html`
- [x] XRP $2 Odds on Polymarket: August 2026 (event: a crypto-market-wide
  short squeeze liquidated over $1.25 billion in leveraged positions
  overnight into Saturday, August 22, 2026, while whale wallets added
  roughly 300 million XRP over the preceding several days and spot XRP
  ETFs logged a $13.2 million net inflow on August 20 - all building on
  President Trump's August 19 White House crypto meeting with Ripple CEO
  Brad Garlinghouse and other executives, where Trump pushed Congress to
  pass the CLARITY Act; XRP traded at $1.59 (+21.4% on the day, ~40% on
  the week) as of 07:08 UTC August 22, and The Block reported it crossed
  $1.40 for the first time in months; Polymarket's "What price will XRP
  hit in August?" ladder repriced across the board - $1.60 to
  effectively-settled 99.9c, $1.80 from under 1c to 36c, $2.00 from under
  1c to 19.7c - while the separate "Clarity Act signed into law in 2026?"
  market, covered on this blog August 7 at 13c, moved far more slowly to
  25c over the same stretch) - 2026-08-22,
  `site/blog/xrp-2-dollar-odds-polymarket-august-2026.html`
- [x] NATO x Russia Clash Odds on Polymarket: August 2026 (event: overnight
  August 19-20, 2026, Russia hit Kyiv with a mass missile and drone
  barrage - at least 15 dead per Mayor Klitschko, around 40 injured per
  President Zelensky, a children's hospital and residential buildings
  damaged - while in the same window a Russian drone tied to a strike on
  Ukrainian Danube ports crossed into Romanian airspace near Galați,
  prompting two Spanish NATO F-18s and a Romanian helicopter to scramble
  (the drone crashed on its own, no intercept), a separate Romanian F-16
  shot down a different explosive-laden drone near the Neptun Deep gas
  field, and Poland's command put aircraft on preventive alert; Polymarket's
  "NATO x Russia military clash by...?" ladder spiked on the headlines -
  the August 31 contract from 2.85c to a 56.5c peak at 15:30 UTC August 20,
  October 31 from 12.5c to the same 56.5c peak, December 31 from 22.5c to
  69c - then fully round-tripped back down by the morning of August 21 (Aug
  31 to 3.6-3.8c, Oct 31 to 13.5c, Dec 31 to 24.5c) once it became clear
  neither incident cleared the market's own resolution bar, which
  explicitly excludes airspace violations and interceptions of munitions
  aimed at a third party) - 2026-08-21,
  `site/blog/nato-russia-clash-odds-polymarket-august-2026.html`
- [x] Bitcoin $70,000 Odds on Polymarket: August 2026 (event: bitcoin broke
  $69,000 for the first time in two months on Wednesday, August 19, 2026,
  after the U.S. Treasury said Wednesday morning it would at least double
  its long-end liquidity-support buyback size (from a $2B cap to a $4B
  minimum per operation, covering 10-20yr and 20-30yr securities, effective
  September 9) and the SEC's crypto task force proposed "Regulation Crypto
  Assets" the prior afternoon (registration exemptions up to $5M over four
  years or $75M/year for larger issuers) - together triggering $1.92B in
  crypto futures liquidations, $1.7B of it inside one four-hour window;
  Polymarket's "What price will Bitcoin hit in August?" ladder repriced with
  it - the $70,000 contract went from under 10c to 99.95c and its order book
  emptied out entirely, while $72,500 jumped from about 4c to a 48.8c/48.9c
  coin flip (+45.7pts on the day), with $75,000 at 22.8c/23c and $77,500 at
  11.3c/11.4c also still actively priced) - 2026-08-20,
  `site/blog/bitcoin-70000-odds-polymarket-august-2026.html`
- [x] Kostyantynivka Capture Odds on Polymarket: August 2026 (event: Polymarket's
  "Will Russia capture Kostyantynivka by...?" capture-by-date ladder - which
  resolves only when the ISW Ukraine control map shades the city's railroad
  station red for Russian control, with that shading required to persist
  through the next full ISW daily update cycle - had faded for three days,
  the September 30 contract sliding from 70.5c on August 15 to a 62c low at
  18:00 UTC August 18 and the August 31 contract drifting from the mid-30s
  to 32c over the same window, then both gapped to the high 90s within the
  next hour (Sep 30 to 98.95c, Aug 31 to 98.35c, and the December 31, 2026
  contract from an 86.75-87.1c band to 99.85c); ISW's own August 18
  assessment described Russian forces "likely consolidat[ing] some
  positions ... which they had previously infiltrated" rather than a
  captured station, and traders posting in the event's comment thread
  through 19:18 UTC still described the ISW map as not showing the station
  under Russian control - the price moved before the market's own
  resolution source had) - 2026-08-19,
  `site/blog/kostyantynivka-capture-odds-polymarket-august-2026.html`
- [x] Florida Republican Governor Primary Odds on Polymarket: August 2026
  (event: Florida's Republican gubernatorial primary, held August 18, 2026 -
  Trump-endorsed Rep. Byron Donalds priced above 95c on Polymarket every day
  since at least July 1 and closed at 98.85c on primary day, unmoved by
  Agriculture Commissioner Wilton Simpson's July 3 endorsement completing a
  sweep of Florida's statewide Cabinet or by rival Lt. Gov. Jay Collins's
  August 13 Florida Phoenix interview calling it a "two-person race" (his
  contract stayed at 0.05c); the genuine two-sided market sat one level
  down, in a separate ladder pricing runner-up James Fishback's primary
  vote share at 49c for under 10%, 37c for 10-15%, and single digits above
  that) - 2026-08-18,
  `site/blog/florida-republican-governor-primary-odds-polymarket-august-2026.html`
- [x] How to Follow a Trader's Portfolio on Polymarket (fallback/evergreen:
  search a trader (/, tab to TRADERS), preview their top positions, follow
  with space, and check back from the watchlist's Traders tab - worked with
  a live example, wallet 0x392a...49262d ("Maru.lucky.nala.lenu"), $10,976
  in positions and +$1,524.06 all-time profit on $247,562 volume across 220
  markets, whose largest position is a "No" bet on the US-Iran 60-day
  extension market this blog covered August 15) - 2026-08-17,
  `site/blog/how-to-follow-a-traders-portfolio-on-polymarket.html`
- [x] Brazil Presidential Election Odds on Polymarket: August 2026 (event: a
  Quaest/Globo poll fielded August 10-13, 2026 and published August 15 put
  Lula at 43% versus Flavio Bolsonaro at 40% in a simulated runoff - within
  the poll's 2-point margin of error and tighter than the 44-39 spread
  Quaest found August 5; Polymarket's "Brazil Presidential Election" market,
  which resolves on the actual winner including any second round, barely
  moved - Lula's contract held a 63.5-66.5c band all month and closed at
  65.5c, while Flavio Bolsonaro's contract crept from about 25c on August 1
  to 28.75c now, a slow multi-week grind rather than a poll-driven jump) -
  2026-08-16,
  `site/blog/brazil-presidential-election-odds-polymarket-august-2026.html`
- [x] US-Iran Ceasefire Extension Odds on Polymarket: August 2026 (event: the
  60-day negotiation window opened by the June 2026 Islamabad MOU closes
  around August 17, 2026; Polymarket's "US-Iran 60 day negotiation period
  extended?" contract fell from a 76.5c high on August 6 after Iranian
  Foreign Minister Abbas Araghchi said August 9 that Tehran was not in
  active talks and would not resume until the US ended its July strikes and
  paid compensation, and Trump added his own compensation demand August 10;
  an August 12 Anadolu report that the US and Iran had "agreed to extend"
  the deadline, sourced to an unnamed mediation contact and never publicly
  confirmed by either government, briefly popped the contract from 29.5c to
  a 41.5c intraday high before it fell back within 90 minutes and kept
  fading to a 12.5-13c low by August 15) - 2026-08-15,
  `site/blog/us-iran-ceasefire-extension-odds-polymarket-august-2026.html`
- [x] Clacton By-Election Odds on Polymarket: August 2026 (event: Nigel
  Farage resigned his Clacton seat on July 7, 2026 to force a by-election
  and re-contest it, after reporting surfaced an undeclared 5 million pound
  personal gift from crypto financier Christopher Harborne plus 25 million
  pounds Harborne gave directly to Reform UK, and a separate arrangement
  with George Cottrell; with Labour, the Conservatives, the Lib Dems and
  the Greens all declining to contest a record 34-candidate ballot,
  Polymarket's "Will Nigel Farage win the Clacton by-election?" market
  opened at 87c the day of the resignation and climbed to a 99.3c peak by
  August 10, while satirist Count Binface - his most recognizable
  opponent by default - rose to an 8.35c high on July 9 before fading
  under 1c by polling day, August 13) - 2026-08-13,
  `site/blog/clacton-by-election-odds-polymarket-august-2026.html`
- [x] Wisconsin Governor Primary Odds on Polymarket: August 2026 (event: Wisconsin's
  Democratic gubernatorial primary, held August 11, 2026 - Polymarket had
  Francesca Hong pricing near 96c to win the nomination through election day
  over Milwaukee County Executive David Crowley's roughly 4c, then returns
  after the 8pm CT poll close flipped it: Crowley's contract crossed 50c
  five times between 01:27 and 03:40 UTC August 12, dipping to a 23.25c low
  before pulling away for good, reaching 99.65c by 07:15 UTC; the AP called
  the race for Crowley at 2:34am CT (07:34 UTC), with the final count
  showing roughly a half-point/1,200-vote margin) - 2026-08-12,
  `site/blog/wisconsin-governor-primary-odds-polymarket-august-2026.html`
- [x] WTI Crude Oil Odds on Polymarket: August 2026 (event: oil prices
  climbed through the weekend into Monday August 10-11, 2026, as the UAE
  reported an Iranian missile strike on an ADNOC-linked tanker in the
  Strait of Hormuz (Saturday August 8), Iran named 16-year IRGC commander
  Mohsen Rezaei as secretary of its Supreme National Security Council
  (Sunday August 9, replacing Zolghadr), and Trump publicly countered
  Iran's reparations demand with one of his own (Monday August 10),
  sending Brent up over 4% to above $87 and WTI near $82; Polymarket's
  "Will WTI Crude Oil hit (HIGH) $85 in August?" rose from 45.5c to an
  87.5c high, while "hit (LOW) $75?" fell from a 92.5c peak to 48.5c) -
  2026-08-11, `site/blog/wti-crude-oil-odds-polymarket-august-2026.html`
- [x] How to Paper-Trade Polymarket Without Risking Money (fallback/evergreen:
  dry-run mode as practice against the real live order book - full
  validation and signing pipeline, no simulated fills - worked with a live
  example from Polymarket's September 2026 Fed "no change" market) -
  2026-08-10, `site/blog/paper-trading-on-polymarket.html`
- [x] US-Iran Blockade End Odds on Polymarket: August 2026 (event: Mohammad
  Bagher Zolghadr, secretary of Iran's Supreme National Security Council,
  published Iran's conditions for reopening the Strait of Hormuz on Saturday
  August 8, 2026 - lift the US naval blockade, withdraw US forces, pay war
  reparations, lift sanctions, release frozen assets - derailing Iran-Oman
  shipping-corridor talks that Foreign Minister Araghchi had called "very
  close" to done a day earlier; Polymarket's "US announces end of Iranian
  blockade by August 15?" fell from a 64.5c Friday-evening peak to a 26.5c
  low (settling 28.5c), the by-August-31 contract fell from 79.5c to 58.5c,
  and the by-August-22 contract saw the ladder's largest 24h move at -35.5c)
  - 2026-08-09, `site/blog/us-iran-blockade-end-odds-august-2026.html`
- [x] Fed September 2026 Odds on Polymarket: The Jobs Report Flip
  (event: the BLS's July 2026 employment report, released 12:30 UTC August
  7, showed nonfarm payrolls falling 23,000 versus a consensus of +83,000,
  with unemployment ticking down to 4.1% on a shrinking labor force and
  wage growth slipping to 3.2% YoY; Polymarket's "Fed Decision in
  September?" market flipped within the hour - "No change" jumped from
  48.5c to a 65.5c intraday peak (settling 62-63c), while "Hike 25bps",
  the favorite since the July 30 FOMC hold at 56.5c and as high as 59.5c
  on August 1, crashed to a 31.5c low (settling 36-37c)) - 2026-08-08,
  `site/blog/fed-september-2026-odds-jobs-report-flip.html`
- [x] Clarity Act Odds on Polymarket: August 2026 (event: the Senate left
  Washington for its August recess on August 7, 2026 without a floor vote on
  the Digital Asset Market Clarity Act (H.R.3633), after Majority Leader
  Thune confirmed August 6 there would be no August vote and pointed to
  September when the chamber returns September 14; Polymarket's "signed
  into law in 2026?" market fell from a 38.5c high on July 24 to 13c, with a
  sharp step from 22.5c to 14.5c on August 5 as reporting turned to the
  Senate running out of floor time, driven by an unresolved ethics dispute
  over Trump's crypto earnings between Sens. Gallego and Alsobrooks and
  Senate Republicans) - 2026-08-07,
  `site/blog/clarity-act-odds-polymarket-august-2026.html`
- [x] Strait of Hormuz Reopening Odds on Polymarket: August 2026
  (event: a Houthi ballistic-missile attack on the Saudi tanker Wafa in the
  Red Sea off Yanbu, August 5, 2026 - the eighth Saudi tanker targeted since
  the July 22 blockade began - landed the same day Trump told Fox News a
  deal to reopen the Strait of Hormuz could come "tomorrow or the next day";
  Polymarket's "Strait of Hormuz traffic returns to normal by August 31?"
  market had climbed from 6.5c to an 18.5c peak on Bloomberg's August 4
  "traffic at a trickle" report and progress on an Iran-Oman shipping-route
  framework, then pulled back to 15.5c after the attack, while the tighter
  "by August 15?" contract fell from 3.2c to 1.65c over the same 24 hours)
  - 2026-08-06, `site/blog/strait-of-hormuz-reopening-odds-august-2026.html`
- [x] Reading the Polymarket Trade Tape (fallback/evergreen: prints vs. the
  book, aggressor side, size and clustering, worked with a live example from
  Polymarket's September 2026 Fed "no change" market) - 2026-08-05,
  `site/blog/reading-the-polymarket-trade-tape.html`
- [x] Michigan Democratic Senate Primary Odds on Polymarket: August 2026
  (event: Michigan's Democratic primary for Gary Peters's open Senate seat,
  held August 4, 2026, between Rep. Haley Stevens and Abdul El-Sayed;
  El-Sayed's Polymarket win-probability contract fell from 81.5c to a 63.5c
  low on July 25 after Gov. Whitmer endorsed Stevens, then climbed to 98.1c
  by primary day as four polls showed him leading by 10-19 points after the
  July 27 debate) - 2026-08-04,
  `site/blog/michigan-democratic-senate-primary-odds-2026.html`
- [x] Limit vs market orders on Polymarket (and why market orders are really
  marketable limits) - 2026-08-03,
  `site/blog/limit-vs-market-orders-on-polymarket.html`
- [x] Iran Strike Cancellation Odds on Polymarket: August 2026
  (event: CBS News reported July 31 that the US and Israel were preparing a
  weekend bombing campaign on Iran's energy infrastructure; Trump announced
  Saturday night, August 1, that he'd canceled the attack after Iran's FM
  reportedly agreed to a Strait of Hormuz compromise brokered by Qatar and
  the US, with Saudi Arabia's MBS also pushing for de-escalation; Iran's
  military disputed Trump's framing but confirmed no strikes occurred;
  Polymarket's "Israel x Iran ceasefire continues through..." ladder jumped
  19-31c across every date within the hour, e.g. the Aug 15 contract rising
  from a 33.5c Saturday low to 85.5c) - 2026-08-02,
  `site/blog/iran-strike-cancellation-odds-august-2026.html`
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
