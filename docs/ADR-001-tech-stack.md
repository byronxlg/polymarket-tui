# ADR-001: Tech stack for polymarket-tui

**Status:** Proposed
**Date:** 2026-07-03
**Deciders:** Byron

## Context

We are building a TUI client with feature parity to the polymarket.com web UI. The hard
requirements that shape the stack choice:

1. **Order signing.** Polymarket orders are EIP-712 typed-data signatures against the CLOB V2
   exchange contracts on Polygon, with proxy-wallet (signature type 1) support. Getting this
   wrong means rejected or (worse) unintended orders. Since the April 2026 V2 migration,
   V1-signed orders are rejected with `order_version_mismatch`, and the V2 `/auth/api-key`
   endpoint is Cloudflare-blocked, requiring a V1-client bootstrap for L2 credentials.
   This is subtle, poorly documented, and already solved in this environment.
2. **Live data.** Order books and prices stream over WebSocket; the UI must handle dozens of
   concurrent subscriptions plus REST polling without blocking the render loop.
3. **Rich TUI.** Feature parity means tables, charts, forms, modals, tabs, scrollable panes,
   and mouse support - a real widget framework, not raw ANSI.
4. **Single user, single machine.** No scale, latency, or deployment constraints. Optimizing
   for correctness of trading code and development speed.

## Decision

**Python 3.12 + Textual (TUI) + py-clob-client-v2 (signing/CLOB) + httpx (REST) +
websockets (streaming) + plotext via textual-plotext (charts) + uv (packaging).**

## Options considered

### Option A: Python + Textual + py-clob-client-v2

| Dimension | Assessment |
|---|---|
| Complexity | Low - signing, auth bootstrap, and every CLOB call already proven working here |
| Order-signing risk | Lowest - reuse py-clob-client-v2 exactly as the working `polymarket` skill does |
| TUI capability | High - Textual has CSS-like styling, widgets, async-native event loop, testing via Pilot |
| Async model | Native - Textual runs on asyncio; httpx/websockets integrate directly |
| Performance | Adequate - book rendering at 10-20 updates/sec is well within Textual's range |
| Distribution | `uv tool install` / `uvx`; venv-based, fine for a personal tool |

**Pros:** the entire authenticated trading path (V1 cred bootstrap, V2 signing, tick-size and
min-size quirks) is already de-risked in this environment; fastest path to a working trading
client; Textual is the most productive TUI framework in any language; charts solved via
textual-plotext.
**Cons:** Python startup ~300ms; single-binary distribution requires pyinstaller (not needed
for personal use); GC pauses theoretically visible under heavy book churn (not at our rates).

### Option B: Go + bubbletea + go-order-utils

| Dimension | Assessment |
|---|---|
| Complexity | Medium-high - official Go CLOB client exists but is V1-era; V2 signing would need porting |
| Order-signing risk | High - would have to re-derive the V2 order struct and the Cloudflare workaround from scratch |
| TUI capability | Medium - bubbletea is solid but lower-level; tables/forms/modals all hand-rolled via lipgloss |
| Distribution | Best - single static binary |

**Pros:** single binary, low memory, no venv.
**Cons:** re-implementing V2 signing is exactly the risk we must not take on a tool that
moves real money; charting in bubbletea is primitive; slower to build every screen.

### Option C: Rust + ratatui

| Dimension | Assessment |
|---|---|
| Complexity | High - no maintained Polymarket CLOB crate; EIP-712 via ethers-rs from scratch |
| Order-signing risk | Highest |
| TUI capability | Medium - ratatui is immediate-mode; forms/modals/focus management all manual |

**Pros:** performance headroom we do not need.
**Cons:** longest build time by far; all API/signing work from zero.

## Trade-off analysis

The decisive factor is order signing. Options B and C both require re-implementing the CLOB V2
EIP-712 order path, including the undocumented V1-bootstrap-for-L2-creds workaround. That is
weeks of risk-laden work to gain distribution/performance properties irrelevant to a
single-user tool. Textual is also simply the strongest TUI framework of the three for
form-heavy, multi-screen apps, which is what "web UI parity" demands.

## Consequences

- Easier: every CLOB interaction can be lifted from the proven `polymarket` skill patterns;
  UI iteration is fast (Textual live-reload dev mode, CSS styling).
- Harder: distribution beyond this machine (acceptable); if Polymarket ships breaking client
  changes we depend on py-clob-client-v2 keeping up (mitigation: the API layer wraps it behind
  our own interface, api-reference.md documents raw endpoints as fallback).
- Revisit if: py-clob-client-v2 is abandoned, or the tool needs to be shared as a binary.

## Pinned stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Packaging | uv (`pyproject.toml`, `uv.lock`) |
| TUI framework | textual >= 0.80 |
| Charts | textual-plotext |
| CLOB client / signing | py-clob-client-v2 (+ legacy py-clob-client for cred bootstrap only) |
| REST | httpx (async) |
| WebSocket | websockets |
| Models | pydantic v2 |
| Config/secrets | Doppler (`polymarket-tui` project) - see config-and-auth.md |
| Tests | pytest + pytest-asyncio + textual Pilot; respx for HTTP mocking |
| Lint/format | ruff |

## Action items

1. [ ] `git init`, scaffold `pyproject.toml` with uv
2. [ ] Create `polymarket-tui` Doppler project, seed dev config (see config-and-auth.md)
3. [ ] Implement API layer against api-reference.md
4. [ ] Build M0 read-only browse screens (see roadmap.md)
