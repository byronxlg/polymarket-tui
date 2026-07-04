# polymarket-tui

Terminal client for Polymarket (Python 3.12 + Textual). Browsing, live order
books, charts, portfolio, and order placement against the real exchange.

@.claude/rules/design-principles.md

## Commands

```sh
uv sync                 # install deps (uv-managed venv)
uv run polymarket-tui   # run the app
uv run pytest -q        # tests (order validation, credstore)
uv run ruff check src/ tests/
```

## Credentials setup (required for account/trading features)

The app reads `~/.config/polymarket-tui/credentials.toml` (plaintext, chmod
600). Create or update it through the credstore, never by echoing the key:

```sh
uv run python -c "
from polymarket_tui.core.credstore import save_credentials
import os
save_credentials(os.environ['POLYMARKET_FUNDER'], os.environ['POLYMARKET_PRIVATE_KEY'], 1)
"
```

On this machine the source of truth for the key material is Doppler
(`global/home` config: POLYMARKET_FUNDER, POLYMARKET_PRIVATE_KEY,
POLYMARKET_SIGNATURE_TYPE) - run the snippet above under
`doppler run --project global --config home --`.

`POLYMARKET_*` env vars override the file when set. The file never stores
the live-trading flag: every session starts in DRY mode (orders are signed
but not posted). LIVE requires the in-app auth-screen toggle or
`POLYMARKET_EXECUTION_LIVE=1` per session. Never enable LIVE or place/cancel
real orders unless the user explicitly asks.

## Verifying changes

Drive the real app in an isolated tmux session against the live APIs:

```sh
tmux -L pmtui new-session -d -x 200 -y 50 'uv run polymarket-tui; sleep 60'
tmux -L pmtui send-keys <keys>; tmux -L pmtui capture-pane -p
tmux -L pmtui kill-server
```

Probe unknown API fields with curl before coding against them (Gamma:
gamma-api.polymarket.com, CLOB: clob.polymarket.com, portfolio:
data-api.polymarket.com). Field quirks are pinned in docs/api-reference.md.

## Architecture

`src/polymarket_tui/`: `core/` (config, credstore, auth bootstrap, ntp, fmt),
`models/` (pydantic; Gamma JSON-string quirks absorbed here), `api/` (async
httpx clients; py-clob-client-v2 wrapped behind asyncio.to_thread),
`services/` (orders validation/placement, portfolio caching), `state/`
(watchlist), `ui/` (Textual screens + widgets). docs/architecture.md has the
full picture; docs/trading.md is the money-path spec - read it before
touching services/orders.py or the order panel.

Trading path invariants (see .claude/rules/design-principles.md for the rest):
- hard-block only what the exchange would reject; warnings rare
- Decimal end-to-end; cents in the UI
- never auto-retry a timed-out post; audit every order/cancel to
  ~/.local/share/polymarket-tui/orders.jsonl
- tests isolate AUDIT_PATH via the autouse fixture - keep it that way

## Gotchas

- A formatter hook runs after every Write/Edit and strips imports that look
  unused mid-refactor; add the import and its usage in the same edit.
- Textual: hidden-but-focusable widgets steal autofocus (disable inputs
  while panels are closed); container widgets need can_focus=True set
  explicitly before .focus() works; Tabs/VerticalScroll consume arrow keys
  unless can_focus=False.
