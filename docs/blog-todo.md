# Blog to-do

Topic queue for the blog at `site/blog/`. The daily workflow
(`.github/workflows/blog-post.yml`) picks the **topmost unchecked topic**,
writes it following `.claude/skills/blog-post/SKILL.md`, and opens a PR.

Rules for the queue:

- Keep it ordered: most valuable next post at the top of the unchecked list.
- One line per topic: working title, then the search intent it targets.
- When a post ships, check it off and append the date and filename.
- Add new ideas at whatever position their value deserves, not just the end.

## Queue

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

- [x] How to read a Polymarket order book - 2026-07-17,
  `site/blog/how-to-read-a-polymarket-order-book.html`
- [x] Prices are probabilities: what a 33c share really tells you - 2026-07-17,
  `site/blog/what-a-polymarket-price-means.html`
