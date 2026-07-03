# Roadmap

Each milestone is shippable and independently useful. Order is chosen so trading (the
risky part) lands after the data layer has been exercised for a while.

## M0 - skeleton + browse (read-only)

- Repo scaffold: uv, ruff, pytest, git init, CI-less (personal tool)
- `core/config.py`, capability-mode detection
- `api/gamma.py` + models: events, markets, tags, search
- Screens: Home (event table, tag bar, sorting, paging), Event, Search, Help
- Watchlist (persist + screen)

Accept: browse trending events by category, open an event, see outcome prices from Gamma
metadata, search, star to watchlist. No CLOB calls yet.

## M1 - market depth + charts

- `api/clob.py` public reads: book snapshot, price, prices-history (to_thread wrapper)
- Market screen: book widget (REST snapshot, `r` to refresh), price chart with intervals,
  YES/NO toggle
- data-api `/trades` recent-trades panel if endpoint confirms, else omit

Accept: open any market, see a correct book (spot-check against the web UI), chart renders
all intervals.

## M2 - live streaming

- `api/ws.py` + `services/stream.py`: market channel, reconnect w/ backoff, resubscribe,
  refcounted subscriptions, staleness detection, poll fallback
- Book widget goes live; last-trade ticker; chart live ticks
- **First task: capture real WS frames and pin them as test fixtures** (message shapes in
  api-reference.md are unverified)

Accept: book on the Market screen visibly updates in real time and matches the web UI;
pulling the network cable degrades to polling with a stale badge, then recovers.

## M3 - portfolio (observer mode)

- `api/data.py`: positions, value, activity
- Auth bootstrap (`core/auth.py`), CLOB authenticated reads: balance, open orders, trades
- Portfolio screen (3 tabs), Activity screen, header balance bar
- User WS channel: live order/fill updates into the open-orders tab

Accept: positions and P&L match the web UI's portfolio page to the cent; balance matches;
open orders stream in when placed from the web UI.

## M4 - trading

- `services/orders.py` validation pipeline (dense unit tests, table-driven)
- Order form + confirm modal + dry-run mode; session order log (JSONL)
- Placement, cancel single / per-market / cancel-all with typed confirmation
- Error mapping incl. the timeout-reconciliation rule (never auto-retry a post)
- Live-fire only behind `POLYMARKET_EXECUTION_LIVE=1`

Accept: in dry-run, full pipeline exercises against live markets logging would-be orders;
then one real small order (5 shares on a liquid penny market) placed, seen filling via WS,
cancelled if resting - verified against the web UI.

## M5 - polish (as-needed backlog)

- Comments read-only on market screen (gamma `/comments`)
- Holders panel (data-api `/holders`)
- Redeemable positions: deep-link/QR to the web UI redeem page
- Settings screen (default TIF, depth, notional threshold)
- Theming, performance passes, `uv tool install` packaging

## Standing risks

| Risk | Mitigation |
|---|---|
| WS message shapes drift / unverified | pin fixtures in M2 before building on them |
| py-clob-client-v2 breakage on Polymarket changes | our `api/clob.py` wrapper is the only import site; raw endpoints documented in api-reference.md |
| Gamma field quirks (JSON-encoded strings) | parse at the model boundary with pydantic validators + fixture tests |
| Order posted but response lost | reconciliation rule in trading.md; audit JSONL |
