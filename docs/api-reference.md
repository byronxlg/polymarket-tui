# API reference

Four upstream surfaces. Shapes below were verified against the live APIs on 2026-07-03
(items marked "verify at impl" are from prior knowledge and must be re-checked when built).

| Surface | Base URL | Auth | Used for |
|---|---|---|---|
| Gamma | `https://gamma-api.polymarket.com` | none | discovery, metadata, search, tags |
| CLOB REST | `https://clob.polymarket.com` | none for market data; L2 creds for user state/orders | books, prices, history, orders, balance |
| Data-API | `https://data-api.polymarket.com` | none (keyed by address) | positions, P&L, activity, portfolio value |
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

No native market order: use marketable limit (cross the spread) + FAK.

Cancels: `client.cancel(order_id)`, `cancel_orders([ids])`, `cancel_all()`,
`cancel_market_orders(market=condition_id, asset_id=token_id)`.

Known rejection strings to map to user-facing errors: `not enough balance / allowance`,
`invalid tick size`, `minimum size`, `order_version_mismatch` (means V1 signing - bug).

## 3. Data-API - portfolio and activity

Keyed by proxy-wallet address (`POLYMARKET_FUNDER`). No auth: it is public on-chain-derived
data. This is what the web UI's portfolio page uses.

### GET /positions?user=0x...&limit=&offset=

Verified fields per position:

```
asset (token id), conditionId, eventId, eventSlug, slug, title, icon,
outcome, outcomeIndex, oppositeAsset, oppositeOutcome,
size, avgPrice, initialValue, curPrice, currentValue,
cashPnl, percentPnl, realizedPnl, percentRealizedPnl, totalBought,
redeemable, mergeable, negativeRisk, endDate, proxyWallet
```

This single endpoint gives the entire positions table including P&L - no client-side
computation needed. Additional params worth verifying at impl: `sortBy=CURRENT|CASHPNL`,
`sizeThreshold`, `redeemable=true`.

### GET /value?user=0x...

Verified: `[{"user": "0x...", "value": 9.4937}]` - total portfolio value (positions
mark-to-market). Header-bar stat alongside USDC cash balance from CLOB.

### GET /activity?user=0x...&limit=&offset=

Verified fields: `type` (TRADE/SPLIT/MERGE/REDEEM/REWARD/CONVERSION - verify full enum),
`side`, `size`, `usdcSize`, `price`, `outcome`, `title`, `slug`, `eventSlug`,
`conditionId`, `asset`, `timestamp`, `transactionHash`, plus profile fields.
Backs the activity screen. Param `type=TRADE` filters.

### Other endpoints (stretch, verify at impl)

`/trades?market=<conditionId>` - public recent trades for a market (the web UI's
"activity" tab on a market page). `/holders?market=` - top holders.

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
- `tick_size_change` - market's tick changed (price nearing 0/1). Not acted on yet.
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
`data-api` positions carry `asset` (token id) + `conditionId` + `eventSlug`, so joining
back to Gamma metadata is direct.
