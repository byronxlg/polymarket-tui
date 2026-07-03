# polymarket-tui

Terminal client for Polymarket. Current build is read-only: browse, order books,
price charts, search, watchlist. Trading is designed (see `docs/`) but not built yet.

## Run

```sh
uv run polymarket-tui
```

No credentials needed for the current feature set - all data comes from public
endpoints (gamma-api, clob).

## Keys

- arrows or `j/k` move; `right`/`>`/`enter` open selected; `left`/`<`/`escape` back
- `q` quit, `/` search, `w` watchlist, `?` full help
- Home: `tab`/`shift+tab` switch category (also `h/l`), `o` cycle sort, `W` star
- Event: multi-outcome chart, `1-6` interval, `c` toggle chart, `i` rules
- Market: `t` flip YES/NO book, `1-6` chart interval (1H 6H 1D 1W 1M ALL)
- A preview rail on the right follows the highlighted row on every list screen

Order book auto-refreshes every 3 seconds.

## Design docs

`docs/README.md` indexes the full design: architecture, API reference (verified
against the live APIs), UI spec, trading design, config/auth, roadmap.
