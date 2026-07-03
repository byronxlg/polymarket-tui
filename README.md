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

- `j/k` move, `enter` open, `escape` back, `q` quit
- `/` search, `w` watchlist, `?` full help
- Home: `[` `]` switch category, `o` cycle sort, `W` star to watchlist
- Market: `t` flip YES/NO book, `1-6` chart interval (1H 6H 1D 1W 1M ALL)

Order book auto-refreshes every 3 seconds.

## Design docs

`docs/README.md` indexes the full design: architecture, API reference (verified
against the live APIs), UI spec, trading design, config/auth, roadmap.
