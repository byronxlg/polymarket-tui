# Roadmap

## Shipped

- M0 browse: home dashboard with category tabs and sort, event pages,
  search (markets + traders, tab-toggled modes), watchlist (events + traders)
- M1 depth/charts: live-polling order book, smooth box-drawing charts with
  crosshair inspect, multi-outcome event charts
- M3 account: auth screen with persisted credentials, capability modes
  (RO/OBS/DRY/LIVE), portfolio with P&L chart, positions, open orders,
  history, trader profile screens
- M4 trading: inline order panel under the live book, warn-only validation,
  dry-run default with per-session live opt-in, cancel with audit, JSONL
  order log
- Extras beyond the original plan: related markets via series (dailies),
  live trades rail with trader drill-in, comments, millisecond NTP-corrected
  clock, follow traders

## Remaining

- M2 websocket streaming (book/prices/user fills) - the book still polls
  every 3s; ws-subscriptions-clob.polymarket.com message shapes need
  capturing and pinning as fixtures first
- Live order verification: one real small order placed/cancelled in LIVE
  mode (everything up to posting is verified; posting itself only dry-run)
- Order status reconciliation view after network-unknown placements
- Redeem deep-link for resolved positions

## Standing risks

| Risk | Mitigation |
|---|---|
| py-clob-client-v2 breakage on Polymarket changes | api/ wrappers are the only import sites; raw endpoints documented in api-reference.md |
| Gamma field quirks (JSON-encoded strings) | parsed at the model boundary with pydantic validators |
| Order posted but response lost | never auto-retry; audit JSONL; check Open Orders |
