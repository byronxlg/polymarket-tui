# polymarket-tui design docs

A terminal client for Polymarket covering the functionality of the polymarket.com web UI:
market discovery, live order books, charts, trading, and portfolio management.

## Documents

| Doc | Contents |
|---|---|
| [design-principles.md](design-principles.md) | UX and code principles distilled from building the app |
| [ADR-001-tech-stack.md](ADR-001-tech-stack.md) | Tech stack decision: Python + Textual + py-clob-client-v2 |
| [architecture.md](architecture.md) | Layers, async model, data flow, project layout |
| [api-reference.md](api-reference.md) | All four API surfaces with live-verified shapes and quirks |
| [trading.md](trading.md) | Order entry, warn-only validation, confirmation, audit |
| [config-and-auth.md](config-and-auth.md) | Credentials file, capability modes, auth bootstrap |
| [roadmap.md](roadmap.md) | Shipped milestones and remaining work |

## Scope summary

**In scope** (parity with polymarket.com):

- Browse trending events, filter by category/tag, sort by volume/liquidity/end date
- Full-text search (events, markets, profiles)
- Event pages: all child markets with prices, 24h change, volume
- Market pages: live order book, price chart, recent trades, spread/midpoint
- Order entry: limit + marketable-limit orders, GTC/GTD/FOK/FAK, buy/sell either outcome
- Portfolio: positions with live P&L, open orders, trade history, USDC balance, portfolio value
- Cancel orders (single, all, per-market)
- Watchlist (local persistence)
- User activity feed
- Live streaming updates via CLOB WebSocket (book, prices, own orders/fills)

**Out of scope** (require on-chain transactions the web UI performs via its embedded relayer,
or are social features with low TUI value):

- Deposits, withdrawals, token approvals (one-time setup done in the web UI)
- Redeeming resolved positions on-chain (positions show a `redeemable` flag; the action links out)
- Position merge/split (CTF operations)
- Comments (read-only display is a stretch goal), profile editing, leaderboard
- Embedded sports scores / live game widgets
