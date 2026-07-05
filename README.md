# polymarket-tui

A fast, keyboard-driven terminal client for [Polymarket](https://polymarket.com):
browse markets, watch live order books and trades, chart prices, track your
portfolio and P&L, follow traders, and place orders - without leaving the
terminal.

Built with Python 3.12 and [Textual](https://textual.textualize.io/).

## Install

**One-line install** (installs [uv](https://docs.astral.sh/uv/) if missing,
then installs `polymarket-tui` as a uv tool):

```sh
curl -sSL https://raw.githubusercontent.com/byronxlg/polymarket-tui/main/install.sh | bash
```

**Homebrew** (this repo doubles as the tap):

```sh
brew tap byronxlg/polymarket-tui https://github.com/byronxlg/polymarket-tui
brew install polymarket-tui
```

**From source** (for development):

```sh
git clone https://github.com/byronxlg/polymarket-tui
cd polymarket-tui
uv sync
uv run polymarket-tui
```

Then run `polymarket-tui`.

No credentials needed to browse: markets, books, charts, trades, comments,
and any trader's public positions all work read-only.

## Run it in the browser

The whole TUI can be served over the web behind a landing page - useful for
demos or trying it without a local install:

```sh
uv run polymarket-tui-web          # serves http://localhost:8000
```

- `/` is a landing page (features, keys, install commands).
- `/app` streams the live TUI into the browser via
  [textual-serve](https://github.com/Textualize/textual-serve) (xterm.js over
  a websocket). Each browser tab spawns its own isolated app subprocess.

Every browser session starts in DRY mode, exactly like the terminal app.
Environment overrides: `PMTUI_WEB_HOST`, `PMTUI_WEB_PORT`,
`PMTUI_WEB_PUBLIC_URL` (set the last one when serving behind a reverse proxy
so the websocket URL is correct).

## Account setup

Press `A` in the app:

- **Funder address only** -> observer mode: your positions, P&L, activity.
  This is the wallet address shown in the Polymarket UI.
- **Funder + private key** -> trading mode. The key is the Polygon key that
  controls your Polymarket wallet (signature type 1 for the standard proxy
  wallet). Applied credentials are saved to
  `~/.config/polymarket-tui/credentials.toml` (chmod 600, plaintext - treat
  the file like the key itself). `POLYMARKET_*` env vars override the file.

**Orders are dry-run until you go live**: fully validated and signed but
never posted. Live posting requires the `L` toggle (confirmed) or
`POLYMARKET_EXECUTION_LIVE=1`; the choice persists across sessions and a
LIVE start is announced.
Every placed/cancelled order is appended to
`~/.local/share/polymarket-tui/orders.jsonl`.

Deposits, withdrawals, token approvals, and redemption of resolved positions
are on-chain operations this client does not perform - use the website.

## Keys

One scheme everywhere - press `?` in the app for the full reference:

- **arrows** move; `up`/`down` flow into adjacent panels (category bar,
  chart inspect, search box); `right`/`enter` open; `left`/`esc` step out
  one level (order panel -> expanded view -> screen -> previous screen)
- **tab** cycles the screen's selector: category (home), chart timeframe
  (event/market), pane (portfolio), results mode (search)
- **space** is the contextual toggle: star an event, follow a trader, flip
  the YES/NO book, flip BUY/SELL while ordering, show rules
- Market pages: `b`/`s` order entry under the live book (price in cents,
  empty = market order, up/down = tick), `y`/`n` book side, `a` expand the
  inline trades to full width (right opens the trader), `i` rules,
  `c` comments, `e` parent event
- `/` search (markets and traders), `p` portfolio, `w` watchlist, `A` auth,
  `L` toggle DRY/LIVE for the session (going live asks for confirmation),
  `q` quit

## Data sources

Public Polymarket APIs: `gamma-api.polymarket.com` (markets, events, search,
comments), `clob.polymarket.com` (order books, price history, orders),
`data-api.polymarket.com` (positions, trades, activity),
`user-pnl-api.polymarket.com` (profit history). Trading uses
`py-clob-client-v2` for CLOB V2 order signing.

## Docs

- `.claude/rules/design-principles.md` - the UX/code principles this app follows
- `docs/architecture.md` - layers, async model, caching
- `docs/api-reference.md` - the four API surfaces, verified shapes, quirks
- `docs/trading.md` - the money path: validation, confirmation, audit
- `docs/config-and-auth.md` - credentials, capability modes

Remaining work is tracked in
[GitHub issues](https://github.com/byronxlg/polymarket-tui/issues).

## Disclaimer

Unofficial client, not affiliated with Polymarket. It can place real orders
with real money when you explicitly enable LIVE mode; you are responsible
for your trades. No warranty.
