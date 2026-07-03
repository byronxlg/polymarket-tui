# polymarket-tui

Terminal client for Polymarket: browse, order books, price charts, search,
watchlist, portfolio, and order placement (dry-run by default).

## Run

```sh
uv run polymarket-tui                                            # read-only
doppler run --project polymarket-tui --config dev -- uv run polymarket-tui  # with account
```

Capability modes by env vars: RO (none), OBS (funder only), DRY (key+funder,
orders signed but never posted), LIVE (DRY + POLYMARKET_EXECUTION_LIVE=1).
Press A in the app to view auth status, enter session-only credentials
(never persisted), or toggle DRY/LIVE.
Every placed/cancelled order is appended to
~/.local/share/polymarket-tui/orders.jsonl.

## Keys

- arrows or `j/k` move; `right`/`>`/`enter` open selected; `left`/`<`/`escape` back
- `q` quit, `/` search, `w` watchlist, `?` full help
- Home: `tab`/`shift+tab` switch category (also `h/l`), `o` cycle sort, `W` star
- Event: multi-outcome chart, `1-6` interval, `c` toggle chart, `i` rules
- Market: `t` flip YES/NO book, `1-6` chart interval, `x` chart inspect,
  `b`/`s` buy/sell form
- Portfolio: `p` from anywhere; `tab` switches positions/orders/history; `x` cancels
- A preview rail on the right follows the highlighted row on every list screen

Order book auto-refreshes every 3 seconds.

## Design docs

`docs/README.md` indexes the full design: architecture, API reference (verified
against the live APIs), UI spec, trading design, config/auth, roadmap.
