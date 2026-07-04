# Configuration and auth

## Credentials

Primary flow: press `A` in the app, enter funder address + private key, `ctrl+s`
to apply and test. Applied credentials are persisted to
`~/.config/polymarket-tui/credentials.toml` (created `0600`, directory `0700`,
deliberately outside any git working tree) and loaded on the next start.
`ctrl+d` on the auth screen clears both the session and the file.

The execution-live flag is never persisted - every session starts in dry-run;
live is enabled per session via the auth screen's execution toggle (confirmed
in a modal) or the `POLYMARKET_EXECUTION_LIVE` env var.

`core/credstore.py` owns the file format (three-key TOML). `get_settings()`
resolution order: env vars win when any `POLYMARKET_*` identity var is set,
otherwise the credentials file, otherwise read-only mode.

## Environment variables (override the credentials file)

| Var | Required | Meaning |
|---|---|---|
| `POLYMARKET_PRIVATE_KEY` | for trading + CLOB user state | Polygon EOA key. Never logged, never rendered. |
| `POLYMARKET_FUNDER` | for portfolio + trading | proxy wallet address (the one the web UI shows) |
| `POLYMARKET_SIGNATURE_TYPE` | default `1` | 1 = proxy wallet, 0 = EOA, 2 = Magic/email |
| `POLYMARKET_EXECUTION_LIVE` | default unset | `1` enables real order posting; otherwise dry-run |
| `POLYMARKET_HOST` | default `https://clob.polymarket.com` | override for testing |
| `POLYMARKET_BUILDER_CODE` | optional override | Builders-Program attribution code (`0x`-prefixed bytes32). Unset = the shipped `DEFAULT_BUILDER_CODE` (every install attributes by default). Set a code to self-attribute; `off`/`none`/`0` to disable. Malformed = no attribution + a one-time warning; never blocks. |
| `PMTUI_MAX_NOTIONAL` | default `500` | typed-confirm threshold in trading.md check 8 |

`core/config.py` is a pydantic-settings `Settings` object; everything else reads config
from it, never from `os.environ` directly.

## Capability modes

Derived at startup from which vars are present:

| Mode | Requirements | Capabilities |
|---|---|---|
| `read-only` | none | browse, search, books, charts, watchlist |
| `observer` | `POLYMARKET_FUNDER` only | + positions, P&L, activity (data-api is public-by-address) |
| `trader-dry` | key + funder + sig type | + balance, open orders, full order pipeline ending in logged dry-run |
| `trader-live` | trader-dry + `POLYMARKET_EXECUTION_LIVE=1` | + real order posting |

Mode is shown in the header (`RO` / `OBS` / `DRY` / `LIVE`) and on the help screen.
Missing-credential states name the exact variable to set, per the skill convention.

## CLOB auth bootstrap (`core/auth.py`)

L2 API creds are deterministic from the wallet signature. V2's `/auth/api-key` endpoint is
Cloudflare-blocked, so bootstrap goes through the legacy V1 client:

```python
v1 = V1Client(host, key=key, chain_id=POLYGON, signature_type=sig_type, funder=funder)
creds = v1.create_or_derive_api_creds()          # deterministic, safe to re-derive
client = ClobClientV2(host, chain_id=POLYGON, key=key,
                      creds=ApiCreds(creds.api_key, creds.api_secret, creds.api_passphrase),
                      signature_type=sig_type, funder=funder)
```

- Runs once at startup in a worker (UI does not block on it); result cached in memory only.
- Derived L2 creds (api key/secret/passphrase) are **not** written to disk in v1 of this
  app - re-derivation costs one signature, ~1s at startup.
- On bootstrap failure: log the reason, drop to `observer`/`read-only`, show a banner.
  Never crash on auth problems.
- If V2's auth endpoint gets unblocked, `auth.py` is the single place to simplify.

## Non-secret local state

`~/.local/share/polymarket-tui/`:

| File | Contents |
|---|---|
| `watchlist.json` | list of event slugs |
| `orders.jsonl` | audit log of every placed/cancelled order (no secrets) |
| `settings.json` | UI prefs: default TIF, book depth, theme (future) |

## Dependencies on this machine

- venv managed by uv inside the repo (`uv sync`); does not reuse `~/.venvs/polymarket`.
- `py-clob-client` (V1, bootstrap only) + `py-clob-client-v2` pinned in `pyproject.toml`.
