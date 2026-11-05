# API reference

Four upstream surfaces. Shapes below were verified against the live APIs on 2026-07-03
(items marked "verify at impl" are from prior knowledge and must be re-checked when built).

| Surface | Base URL | Auth | Used for |
|---|---|---|---|
| Gamma | `https://gamma-api.polymarket.com` | none | discovery, metadata, search, tags |
| CLOB REST | `https://clob.polymarket.com` | none for market data; L2 creds for user state/orders | books, prices, history, orders, balance |
| Data-API | `https://data-api.polymarket.com/v2` | none (keyed by address) | positions, P&L, activity, portfolio value |
| CLOB WS | `wss://ws-subscriptions-clob.polymarket.com/ws/` | user channel needs L2 creds | live books, prices, own orders/fills |

Rate limits: CLOB ~50 req/s per key; Gamma/Data-API unspecified - back off on 429.

## 1. Gamma - discovery and metadata

### GET /events

Primary browse endpoint. The web UI's home page is essentially this call.

Params: `limit` (default 100, and a hard ceiling - `limit=500` still returns 100), `offset`,
`active=true`, `closed=false`, `archived=false`,
`order=volume24hr|liquidity|startDate|endDate`, `ascending=false`, `tag_slug`, `tag_id`,
`end_date_min`/`end_date_max` (ISO-8601; `+00:00` and `Z` offsets both accepted).

`active=true&closed=false` does NOT mean "still running". Gamma leaves long-expired events
flagged that way - on 2026-07-09 the first 1000+ rows of `order=endDate&ascending=true` had
end dates months in the past, so an "ending soonest" browse returns nothing but dead markets
and any client-side ended-events filter empties the page (#133). Pass `end_date_min=<now>`
to get a live-only window. It filters out dateless events too, so scope it to the endDate
sort; the other orders carry only a handful of expired rows (0-10 per 100) and the
client-side filter handles those.

Response: array of events. Verified shape (relevant fields):

```json
{
  "id": "30615",
  "slug": "world-cup-winner",
  "title": "World Cup Winner",
  "description": "...",
  "endDate": "2026-07-19T...",
  "volume24hr": 5011906.4,
  "liquidity": ...,
  "tags": [{"id": "1", "label": "Sports", "slug": "sports"}, ...],
  "markets": [ <market objects, see below> ]
}
```

An event groups related markets (a 60-market World Cup event, or a single binary market).
The UI renders events, not bare markets.

### Market object (embedded in events, or via GET /markets)

Verified fields we rely on:

```json
{
  "question": "Will Spain win the 2026 FIFA World Cup?",
  "conditionId": "0x7976...",
  "slug": "will-spain-win-...",
  "clobTokenIds": "[\"43943...\", \"11268...\"]",   // JSON-encoded string! parse it
  "outcomes": "[\"Yes\", \"No\"]",                   // also JSON-encoded string
  "outcomePrices": "[\"0.1225\", \"0.8775\"]",       // also JSON-encoded string
  "bestBid": 0.122,
  "bestAsk": 0.123,
  "spread": 0.001,
  "oneDayPriceChange": 0.023,
  "volume24hr": 5011906.4,
  "endDate": "...",                   // expected resolution time, NOT a trading cutoff
  "active": true, "closed": false,
  "acceptingOrders": true,            // the CLOB's actual order gate; stays true past
                                      // endDate while resolution is pending (verified
                                      // 2026-07-06: weather market, endDate passed,
                                      // live book, acceptingOrders=true)
  "orderPriceMinTickSize": 0.001,     // verify at impl; used for order validation
  "orderMinSize": 5                   // verify at impl
}
```

Gotcha: `clobTokenIds`, `outcomes`, `outcomePrices` are JSON **strings**, not arrays.
`clobTokenIds[0]` corresponds to `outcomes[0]` (YES), `[1]` to NO.

### GET /markets, GET /markets/{id}

Same market objects, filterable directly (`active`, `closed`, `order`, `slug`, ...).
Used for market-by-slug resolution.

### GET /events/{slug} or /events?slug=

Single event with all markets - the event detail screen.

### GET /tags

Verified: `[{"id": "1", "label": "Sports", "slug": "sports"}, ...]`. Drives the category
bar. The web UI's top-nav categories are tags: politics, sports, crypto, economy, tech,
culture, world.

### GET /public-search?q=...

Verified response keys: `{"events": [...], "pagination": {...}}` (also returns `tags` and
`profiles` with `limit_per_type` param - verify at impl). Backs the search screen.
Gamma full-text is limited; for topical browse prefer tag filters + client-side substring.

## 2. CLOB REST

Accessed via `py-clob-client-v2` (wrapped in `api/clob.py`). Public reads work with an
unauthenticated client; user state needs L2 creds (see config-and-auth.md for bootstrap).

### Public

```python
client.get_order_book(token_id)
# {"bids": [{"price": "0.122", "size": "1500"}, ...], "asks": [...]}  (V2 returns dicts)

client.get_price(token_id, side="BUY"|"SELL")   # best executable price
client.get_midpoint(token_id)                    # verify at impl
client.get_spread(token_id)                      # verify at impl
```

### GET /prices-history  (direct REST, no auth)

Verified: `?market=<token_id>&interval=1h|6h|1d|1w|1m|max&fidelity=<minutes>` returns
`{"history": [{"t": 1782982807, "p": 0.0995}, ...]}`. Chart data source.
Interval-to-fidelity mapping used by the web UI: 1h->1, 6h->10, 1d->60, 1w->360, 1m->1440
(verify at impl).

Quirks (all verified 2026-07-07 against the closed Trump-2024 market; every failure
mode below returns `{"history": []}` with HTTP 200, never an error):

- `interval` windows are anchored to **now**. On a closed market every relative
  interval returns empty - except `max`, which spans the market's lifetime and
  works regardless of state (needs an explicit `fidelity`; bare `interval=max`
  returns empty).
- Explicit ranges (`startTs`/`endTs`, epoch seconds, + `fidelity`) also work on
  closed markets, but a single request caps at **15 days** of span - 16 days
  returns empty. Longer windows must be stitched from consecutive requests
  (`ClobPublicClient.prices_history(end_ts=...)` does this).
- `fidelity` only accepts the known values (1, 10, 60, 360, 720, 1440);
  in-between values like 500 return empty. Fine fidelities on long ranges also
  return empty (interval=max + fidelity=60 fails, +720/1440 works) - there is a
  server-side ceiling somewhere below ~900 returned points.

### Market resolution lifecycle (Gamma fields)

`endDate` passing changes nothing (see acceptingOrders above). A market closes when
its oracle resolution finalizes: `closed` flips true, `closedTime` records the halt,
`acceptingOrders` flips false, `outcomePrices` freeze at `["1", "0"]` (the 1 marks
the winner), and the CLOB book empties. `umaResolutionStatus` is null until a
resolution is proposed and reads "resolved" once final (every closed market sampled
carries it). `closedTime` is postgres-style (`"2024-11-06 15:17:41+00"` - space
separator, bare `+00` offset) and needs normalizing before ISO parsing
(`Market._pg_datetime`).

### Authenticated (L2 creds)

```python
client.get_open_orders(OpenOrderParams())        # V2 name; not get_orders
client.get_trades()                              # own trade history
client.get_balance_allowance(BalanceAllowanceParams(
    asset_type=AssetType.COLLATERAL, signature_type=sig_type))
# balance in micro-USDC: divide by 1_000_000
# AssetType.CONDITIONAL + token_id -> share balance for one position (also 6 decimals)
```

### Orders

```python
OrderArgs(token_id, price, size, side="BUY"|"SELL", expiration=..., builder_code=..., metadata=...)
# V2 dropped fee_rate_bps / nonce / taker. expiration only for GTD.
signed = client.create_order(order_args)
resp = client.post_order(signed, OrderType.GTC | GTD | FOK | FAK)
```

Response:

```python
{"success": True, "errorMsg": "", "orderID": "0x...",
 "status": "matched"|"live"|"delayed"|"unmatched",
 "makingAmount": "3.7", "takingAmount": "5", "transactionsHashes": ["0x..."]}
```

`status`: `live` = resting on the book, `matched` = crossed a resting order,
`delayed` = marketable, held in a matching delay, `unmatched` = marketable but
the delay failed (placement still succeeded). **`matched` does not mean fully
filled** - a GTC that crosses a thin book matches part and rests the rest.

**Never derive a fill size from `makingAmount`/`takingAmount`.** Which one is
shares and which is USDC depends on the side, and Polymarket's docs do not
specify it (checked Jul 2026); both are `""` for a `live` order. The only
trustworthy share count is `size_matched`, on the `/ws/user` order frame and on
`GET /orders`. `services/orders.py` reads `success`/`status`/`orderID`/
`errorMsg` and nothing else.

No native market order: use marketable limit (cross the spread) + FAK.

Cancels: `client.cancel(order_id)`, `cancel_orders([ids])`, `cancel_all()`,
`cancel_market_orders(market=condition_id, asset_id=token_id)`.

Known rejection strings to map to user-facing errors: `not enough balance / allowance`,
`invalid tick size`, `minimum size`, `order_version_mismatch` (means V1 signing - bug).

## 3. Data-API - portfolio and activity

Keyed by proxy-wallet address (`POLYMARKET_FUNDER`). No auth: it is public on-chain-derived
data. This is what the web UI's portfolio page uses.

### v2, since v1 was retired (410, first seen 2026-11-02)

Base `https://data-api.polymarket.com/v2`, contract at `/v2/openapi.json`. `data-api` v1,
`lb-api` and `user-pnl-api` all answer 410. Every response is `{data, pagination?}`,
snake_case, amounts as JSON numbers. A null number means unavailable, not zero, so
`models/portfolio.py` drops nulls to the field's default rather than lose the row. Paging is
cursor-only (`next_cursor`, no `offset`); `limit` caps at 1000 and applies to the first page.
`tests/test_data_api_v2.py` holds real rows; its live test runs daily in `api-contract.yml`.

### GET /v2/positions?user=0x...

`status` defaults to `OPEN`: a superset with unredeemed winners, but without resolved losers
(`REDEEMABLE_LOST`) and archived markets (`include_archived=true`). Dust floor 0.1 shares.

Fields the app maps: `token_id` to `asset`, `current_size` to `size`, `current_price` to
`cur_price`, `entry_cost_usdc` to `initial_value`, `unrealized_pnl` to `cash_pnl`. Same name:
`condition_id`, `event_slug`, `slug`, `title`, `outcome`, `outcome_index`, `avg_price`,
`current_value`, `percent_pnl`, `realized_pnl`, `redeemable`, `end_date` (bare date).

### GET /v2/positions?user=0x...&status=CLOSED&sort_by=TIMESTAMP&sort_direction=DESC

Backs the Closed tab. The default order is `REALIZED_PNL`, a highlight reel, so a history must
ask for `TIMESTAMP`.

- `last_event_at` is when it closed. `current_size` is 0; `total_size` is the shares held.
- Return is `percent_realized_pnl`; `percent_pnl` reads 0 here. `total_cost_usdc` is only the
  fees by now: cost is `total_size * avg_price`, which is what the server's percentage uses.
- `current_price` is 1/0 for a position held to resolution but a mid price for one sold out
  beforehand - it does **not** mean won/lost. Only the sign of `realized_pnl` is a fact.

### GET /v2/value?user=0x... and /v2/user-stats?user=0x...

`{data: {proxy_wallet, value}}`: positions mark-to-market. `user-stats` `trades` counts
**distinct markets**, not trades: the "markets" stat on the profile header. `data: null` means
no such user; zeros mean a user who never traded.

### GET /v2/leaderboard?user=0x...&time_period=all

With `user` it answers one object: `{pnl, volume, rank_pnl, rank_volume, ...}`, the profile
header's Profit and Volume. `time_period` defaults to `day`. `profile_stats()` gathers these
routes concurrently and drops any field whose route errored rather than blanking the line.

### GET /v2/user-pnl?user=0x...&interval=1m&fidelity=1d

`{data: {points: [{timestamp, position_pnl, ...}]}}`. `position_pnl` is realized plus unrealized;
the P&L strip plots it.

### GET /v2/activity?user=0x...&limit=

`type`, `side`, `size`, `usdc_size`, `price`, `outcome`, `title`, `slug`, `event_slug`,
`condition_id`, `token_id`, `timestamp`, `transaction_hash`, plus profile fields. Deposits and
withdrawals are excluded unless `exclude_deposits_withdrawals=false`.

### GET /v2/trades?condition=<conditionId>&limit=

Public recent trades for a market. Same row shape without `usdc_size`, derived from size * price.

## 4. CLOB WebSocket

Host: `wss://ws-subscriptions-clob.polymarket.com/ws/`. Two channels. Both market- and
user-channel shapes below are **verified from real captured frames** (see
tests/fixtures/ws_market_*.json and ws_user_*.json, captured 2026-07-04).

Frames arrive **batched as a JSON array** (`[{...}, {...}]`), even for a single message.
Each element carries `event_type`. Timestamps are epoch-ms strings.

### /ws/market  (no auth)

Subscribe: `{"type": "market", "assets_ids": ["<token_id>", ...]}`.
Keepalive: send the text frame `PING` if idle (~10s); the server closes idle sockets.

Messages (each has `event_type`):

- `book` - full snapshot: `{event_type, asset_id, market, bids: [{price, size}...],
  asks: [...], timestamp, hash, tick_size, last_trade_price}`. bids/asks are strings;
  best bid = max bid price, best ask = min ask price.
- `price_change` - deltas. **Real shape differs from earlier docs**: it is
  `{event_type, market, timestamp, price_changes: [{asset_id, price, size, side,
  hash, best_bid, best_ask}, ...]}`. One frame can carry changes for several assets
  in the market, so filter entries by `asset_id`. `side` BUY -> bid level, SELL -> ask.
  `size` is the new absolute level size; "0" removes the level.
- `tick_size_change` - `{event_type, asset_id, market, old_tick_size, new_tick_size,
  timestamp}`. The exchange re-grids a market (typically 0.01 -> 0.001) as its price
  nears 0 or 1. Acted on: LiveBook adopts the new tick and the pane re-renders the
  book and order form at it. **The CLOB is the only authority on the current tick** -
  it is also stamped on every `book` frame and every REST `/book`. Gamma's
  `orderPriceMinTickSize` mirrors it but is snapshotted when a pane opens (and the
  home list can serve one a day old from disk cache), so it is a fallback only.
- `last_trade_price` - trade prints: `{event_type, asset_id, price, side, size,
  timestamp, fee_rate_bps, transaction_hash}`.

Book maintenance (see models/ws.py `LiveBook`): apply snapshot on `book`, patch levels
on each `price_change` entry for the asset, discard frames strictly older than the last
applied timestamp. The UI degrades to REST polling with a stale badge when the socket
is down or no frames arrive for STALE_AFTER_S.

### /ws/user  (auth)

Subscribe: `{"type": "user", "markets": [], "auth": {"apiKey": ..., "secret": ...,
"passphrase": ...}}`. L2 creds are derived via `core.auth.derive_l2_creds` (V1 client's
`create_or_derive_api_creds`, deterministic from the wallet signature). An empty `markets`
list subscribes to all own activity (verified). No initial snapshot - frames only arrive
on order/fill events, so keep REST `get_open_orders` for the baseline.

Messages (verified shapes):

- `order` - own order lifecycle: `{event_type, id, market (condition id), asset_id, side,
  outcome, price, original_size, size_matched, type, status, timestamp, maker_address, ...}`.
  `type` is PLACEMENT / UPDATE / CANCELLATION; `status` is LIVE / MATCHED / CANCELED.
  A LIVE order is (partly) resting; CANCELED or MATCHED means it left the book.
- `trade` - own fills: `{event_type, id, market, asset_id, side, outcome, price, size,
  status, timestamp}`; status walks MATCHED -> MINED -> CONFIRMED. (Shape from prior
  knowledge; not fill-captured in this pass.)

The app runs this socket at the app level (`start_user_channel`): `order`/`trade` frames
toast and refresh the portfolio open-orders tab live, no manual refresh needed.

Keepalive: send `"PING"` text frame every ~10s; server may close idle sockets (verify).

## Cross-surface ID vocabulary

The three IDs and where each is used - a constant source of bugs, so pin it:

| ID | Example | Source | Used by |
|---|---|---|---|
| event id/slug | `world-cup-winner` | Gamma | event pages, URLs |
| conditionId (market) | `0x7976...` | Gamma `conditionId` | data-api positions/trades, WS user channel, cancel_market_orders |
| token id (outcome) | `43943...` (uint256 decimal string) | Gamma `clobTokenIds` | all CLOB book/price/order calls, WS market channel, data-api `asset` |

Mapping: event 1-N markets; market has exactly 2 token ids (YES=index 0, NO=index 1).
`data-api` positions carry `token_id` + `condition_id` + `event_slug`, so joining
back to Gamma metadata is direct.
