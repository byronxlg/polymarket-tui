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

- arrows or `j/k` move; `right`/`>`/`enter` open selected; `left`/`<`/`escape` back
- `q` quit, `/` search, `w` watchlist, `?` full help
- `tab`/`shift+tab` cycle the screen's main selector: category (home),
  chart timeframe (event/market), pane (portfolio); `h/l` are aliases
- Home: `o` cycle sort, `W` star
- Event: multi-outcome chart, `x` inspect (scrub with arrows), `i` rules pane
- Market: `t` flip YES/NO book, `x` inspect, `b`/`s` buy/sell form
- Portfolio: `p` from anywhere; `x` cancels the highlighted order
- A preview rail on the right follows the highlighted row on every list screen

Order book auto-refreshes every 3 seconds.

## Design docs

`docs/README.md` indexes the full design: architecture, API reference (verified
against the live APIs), UI spec, trading design, config/auth, roadmap.
