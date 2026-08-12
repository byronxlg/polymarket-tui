# Post copy

Draft copy for the three shorts. Follows `docs/marketing.md`: disclosed
identity, value first, never the same text twice, low volume. Prices are as at
recording - say "at the time of recording" or re-check before posting a
number.

Log each post in `docs/marketing-log.md` with timestamp, channel, link and the
text actually used, before or immediately after posting.

## 1. speed-cold-start (19s)

**Title** - Cold start to a live Polymarket order book

**Body** - polymarket-tui is a terminal client for Polymarket. Cold start, no
cache: search a market, open it, and the book is streaming over websocket. The
counter is real elapsed time from process launch, including the boot - it also
includes a couple of seconds of deliberate pause so the screen is readable.

uv tool install polymarket-tui

## 2. story-dry-trade (28s)

**Title** - Placing a Polymarket limit order without leaving the terminal

**Body** - The whole money path: cursor the depth you want, `b` prefills the
price from the touch, size in shares, then a review that spells out cost,
payout, and what actually fills now versus what rests on the book. This runs
in dry-run, which signs the order and never posts it - the default for a new
setup, and what you see in the panel.

uv tool install polymarket-tui

## 3. hormuz-term-structure (28s)

**Title** - One question, six expiry dates: reading a Polymarket curve

**Body** - Polymarket prices "Strait of Hormuz traffic returns to normal" at
six separate dates. At the time of recording: ~15c for August, ~27c for
September, ~55c for December. That spread is the market's view on timing, not
just on outcome, and it is easier to read as a ladder than as six separate
pages. The chart underneath is the same market sliding from 48c to 15c over
three weeks.

uv tool install polymarket-tui

## Sequencing

Not all three at once, and not all three on one platform on one day - the low
volume rule applies here as much as to comments.

Lead with #3 on any channel where the audience is prediction-market people
rather than terminal people: it is the only one that stands on its own as an
observation about a market. #1 is the tool demo. #2 is the most useful and the
most likely to attract policy attention, since it shows an order being placed
- prediction markets sit near the gambling and financial promotion lines on
TikTok and Meta. Post it on YouTube first and watch what happens before
repeating it elsewhere.
