# Architecture

## Layer diagram

```
+---------------------------------------------------------------+
|  ui/            Textual App, Screens, Widgets                 |
|                 (render state, emit user intents)             |
+---------------------------------------------------------------+
|  services/      MarketService  PortfolioService  OrderService |
|                 StreamService (WS fan-in -> reactive state)   |
+---------------------------------------------------------------+
|  api/           GammaClient  ClobClient  DataApiClient        |
|                 WsClient (market + user channels)             |
+---------------------------------------------------------------+
|  models/        pydantic domain models (Event, Market,        |
|                 OrderBook, Position, Order, Trade, ...)       |
+---------------------------------------------------------------+
|  core/          config, auth bootstrap, errors, formatting    |
+---------------------------------------------------------------+
```

Dependency rule: arrows point down only. `ui` never imports `api`; screens talk to services.
Services return domain models, never raw JSON. This keeps the four upstream APIs (which
overlap and disagree on field names) behind one coherent vocabulary.

## Project layout

```
polymarket_tui/
  __main__.py            # entry point: config load -> App.run()
  core/
    config.py            # Settings (pydantic-settings, env-driven)
    auth.py              # L2 cred bootstrap (V1 client -> V2 creds), cached
    errors.py            # ApiError, AuthError, OrderRejected, ...
    fmt.py               # money/price/pct/relative-time formatters
  models/
    event.py  market.py  book.py  position.py  order.py  trade.py  activity.py
  api/
    gamma.py             # async httpx wrapper over gamma-api
    clob.py              # wraps py-clob-client-v2 (sync lib -> asyncio.to_thread)
    data.py              # async httpx wrapper over data-api
    ws.py                # websocket manager: market + user channels, reconnect
  services/
    markets.py           # discovery, search, event/market detail, price history
    portfolio.py         # positions, balance, activity, trade history
    orders.py            # validation pipeline, place, cancel
    stream.py            # subscription registry, book maintenance, message dispatch
  state/
    store.py             # AppState: caches, watchlist, subscription refcounts
    watchlist.py         # JSON persistence in ~/.local/share/polymarket-tui/
  ui/
    app.py               # PolymarketApp(Textual App), global bindings, theming
    screens/
      home.py  event.py  market.py  portfolio.py  search.py  watchlist.py  help.py
    widgets/
      event_table.py  book_widget.py  price_chart.py  order_form.py
      confirm_modal.py  positions_table.py  orders_table.py  trades_log.py
      balance_bar.py  tag_bar.py  toast.py
    styles/
      app.tcss           # Textual CSS
tests/
  api/  services/  ui/   # respx-mocked API tests; Pilot-driven UI tests
docs/                    # these documents
```

## Async model

Everything runs on Textual's single asyncio event loop.

- **REST**: `httpx.AsyncClient` (one shared instance per API base URL, HTTP/2, connection
  pooling). Screens call services from `@work` Textual workers so slow calls never block
  rendering; results are applied via reactive attributes or `post_message`.
- **py-clob-client-v2 is synchronous.** All calls to it go through
  `asyncio.to_thread(...)` inside `api/clob.py`. Order signing is CPU-trivial (<10ms), so
  a thread hop is sufficient; no process pool needed.
- **WebSockets**: `services/stream.py` owns two long-lived tasks (market channel, user
  channel). Each is a `websockets` connect-loop with exponential backoff reconnect
  (1s, 2s, 4s ... cap 30s) and resubscribe-on-reconnect. Incoming messages are parsed to
  typed events and dispatched to subscribers via an in-process pub/sub
  (`stream.subscribe(token_id) -> AsyncIterator[BookEvent]` plus a Textual message bridge).
- **Polling fallback**: if the WS is down, `stream` degrades to REST polling of
  `/book` every 3s for actively-viewed tokens and marks the UI stale-indicator.

## Data flow examples

### Viewing a market

```
MarketScreen.on_mount
  -> MarketService.get_market(slug)          # Gamma: metadata, token ids
  -> ClobClient.get_book(token_id)           # initial book snapshot
  -> ClobClient.get_prices_history(token_id) # chart series
  -> StreamService.subscribe([yes_id, no_id])
       ws "book" events    -> replace book widget state
       ws "price_change"   -> patch book levels, update midpoint/spread
       ws "last_trade_price" -> append to trades log, tick chart
MarketScreen.on_unmount -> StreamService.unsubscribe(...)  # refcounted
```

### Placing an order

```
OrderForm submit
  -> OrderService.validate(draft)     # tick size, min size, balance, price-vs-mid
  -> ConfirmModal (always)            # rendered summary incl. notional + warnings
  -> OrderService.place(draft)        # to_thread: create_order + post_order
  -> result toast; user WS channel delivers authoritative order/fill updates
  -> PortfolioService cache invalidated
```

## State and caching

`state/store.py` holds a single `AppState` object owned by the App:

| Cache | TTL / invalidation |
|---|---|
| Event/market metadata (Gamma) | 60s TTL, keyed by slug/id |
| Tag list | process lifetime |
| Order books | live via WS; snapshot refetch on resubscribe |
| Positions, balance | 30s TTL, invalidated on any order placement/fill |
| Open orders | live via user WS channel; REST snapshot on portfolio open |
| Price history | 5min TTL keyed by (token, interval) |
| Watchlist | persisted JSON, loaded at startup |

Books are maintained as sorted dicts (price -> size) per token; `price_change` deltas are
applied in place, `book` messages replace wholesale. A monotonic `timestamp`/hash guard
discards out-of-order messages.

## Error handling

- `api/` raises typed errors: `RateLimited(retry_after)`, `ApiError(status, body)`,
  `AuthError`, `OrderRejected(error_msg)`.
- Services translate to user-facing outcomes; UI shows toasts, never tracebacks.
- 429s: honor retry-after, back off; CLOB read budget is ~50 req/s per key, Gamma
  unspecified. All REST calls go through a small token-bucket limiter in `api/`.
- Auth failure at startup drops the app into **read-only mode** (see config-and-auth.md)
  rather than exiting: browse/books/charts work, portfolio and trading show a banner.

## Testing strategy

- `api/`: respx-mocked httpx tests using captured real payloads (fixtures in
  `tests/fixtures/*.json` recorded from the live API).
- `services/orders.py`: table-driven validation tests (tick size, min size, balance,
  price sanity) - this module gets the densest coverage.
- `ui/`: Textual Pilot integration tests per screen (mount, key presses, assert rendered
  content) with services faked at the boundary.
- One live smoke test (`tests/live/`, opt-in via env flag) that exercises read paths
  against production, mirroring the existing skill smoke test.
