# Landing page words

Every word the landing page may show, and every string it carries for screen readers and search
results. One name per idea. Sentence case, no full stop on labels. `tests/test_site_words.py`
fails if the page shows a word that is not in the Word column, if the page goes over 220 visible
words, or if this file changes without a new entry in `cold-reads.md`.

Commands, keys and the version number are not words: they are checked against the README and
`pyproject.toml` instead.

| Idea | Word |
|------|------|
| The product | polymarket-tui |
| Heading | Polymarket in your terminal |
| Facts under the heading | macOS, Linux |
| The code host (never "Source", never "Repo") | GitHub |
| Install tabs, each named by its tool | uv / Homebrew / curl / git |
| After installing | Then run |
| Copy control states | Copied / Copy failed |
| Recording control | Pause / Play |
| The four stills | Order book / Order review / Price chart / Search |
| Safe mode and real mode (the app's own words) | DRY / LIVE |
| Safety lines (LIVE persists across runs: README "Orders are dry-run until you go live") | New installs start in DRY: orders are never posted. / LIVE posts real orders. L switches between DRY and LIVE, and asks first. It opens in the mode you left. / Browse with no wallet. |
| Where to add an address or key | Add a wallet to trade |
| Keys heading | Keys |
| Key meanings | Move, open, back / Add to Watchlist, or switch the YES and NO order book / Next pane / Buy, Sell / Search / Portfolio, Watchlist / DRY or LIVE / All keys, Quit |
| Footer | Unofficial. Not affiliated with Polymarket. In LIVE it posts real orders with real money. You are responsible for your trades. No warranty. Deposits, withdrawals and redemptions stay on polymarket.com. |
| Footer links | GitHub / Blog / Polymarket |

## Not shown, but read out or indexed

Each must appear on the page exactly as written here.

- Page title: polymarket-tui: Polymarket in your terminal
- Description: A keyboard-driven terminal client for Polymarket: markets, live order books, charts, portfolio and orders.
- Copy button name: Copy install command
- Install tabs name: Install with
- Footer links name: Links
- Feed name: polymarket-tui blog
- Recording: Recording of one polymarket-tui session: a market, its order book, an order in DRY, a price chart and search
- Still: Order book for YES: asks from 18.0c to 18.5c, bids from 17.7c to 17.9c, streaming
- Still: Order review in DRY: buy 5 YES at 17.7c, cost $0.89, payout $5.00 if it wins
- Still: Price chart for YES at 17.9c, from July to October
- Still: Search results for bitcoin: a list of markets with prices
