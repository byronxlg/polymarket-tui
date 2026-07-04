# polymarket-tui

Terminal client for Polymarket: browse, order books, price charts, search,
watchlist, portfolio, and order placement (dry-run by default).

## Run

```sh
uv run polymarket-tui
```

Press A to authenticate: enter your funder address (and private key for
trading). Applied credentials are saved to
~/.config/polymarket-tui/credentials.toml (chmod 600); POLYMARKET_* env vars
override the file when set.

Capability modes: RO (no creds), OBS (funder only - positions and P&L),
DRY (key+funder - orders signed but never posted), LIVE (DRY + the in-app
live toggle or POLYMARKET_EXECUTION_LIVE=1). Live mode is never persisted;
every session starts DRY. Every placed/cancelled order is appended to
~/.local/share/polymarket-tui/orders.jsonl.

## Keys

Core: arrows move (up also enters what is above - category bar, chart,
search box), right/enter open, left/escape back, tab cycles the screen's
selector (category / timeframe / pane), space is the contextual toggle
(star events on lists, flip YES/NO book, show rules). / search, p portfolio,
w watchlist, H home, A auth, ? full key reference, q quit.

Market pages mirror the event page: outcome rows on the left drive the order
book rail on the right; the chart sits in a strip below (a/c swap in live
trades / comments). b/s open inline order entry under the book (price in
cents, empty = market order, up/down tick, enter review, y place).

Search (/) covers markets and traders; follow traders with space and find
them under the watchlist's Traders tab, including their public positions
and activity.

Order book auto-refreshes every 3 seconds.

## Design docs

`docs/README.md` indexes the full design: architecture, API reference (verified
against the live APIs), UI spec, trading design, config/auth, roadmap.
