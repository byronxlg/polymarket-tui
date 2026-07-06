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

## Landing page

A static landing page lives in [`site/`](site/) and deploys to GitHub Pages
(https://byronxlg.github.io/polymarket-tui/). Its hero plays a recorded
asciinema demo of the TUI - browse markets, open one, cursor the live book,
chart, search. Preview it locally with `python3 -m http.server -d site 8000`,
and regenerate the demo with `bash scripts/record_demo.sh`. See
[`site/README.md`](site/README.md).

## Account setup

Press `A` in the app (a pop-out - esc drops you back where you were):

- **Funder address only** -> observer mode: your positions, P&L, activity.
  This is the wallet address shown on your polymarket.com profile (also your
  USDC deposit address).
- **Funder + private key** -> trading mode. Where the key comes from depends
  on how you log in to Polymarket:
  - email/Magic login: polymarket.com -> Settings -> Export Private Key
    (signature type 1, the default)
  - browser wallet: export the key from the wallet itself, e.g. MetaMask
    account details (signature type 2)
  - trading straight from your own wallet with no Polymarket proxy: that
    wallet's key, funder = the same address (signature type 0)

  Applied credentials are saved to
  `~/.config/polymarket-tui/credentials.toml` (chmod 600, plaintext - treat
  the file like the key itself). `POLYMARKET_*` env vars override the file.

  Note: accounts created since Polymarket switched to Privy embedded wallets
  export only a threshold-key share; the trading API (and therefore this
  client) does not support them yet.

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
