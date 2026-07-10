# Architecture

## Layer diagram

```
+---------------------------------------------------------------+
|  ui/            Textual App, Screens, Widgets                 |
|                 (render state, emit user intents)             |
+---------------------------------------------------------------+
|  services/      PortfolioService  OrderService                |
+---------------------------------------------------------------+
|  api/           GammaClient  ClobPublicClient                 |
|                 AuthedClobClient  DataApiClient               |
+---------------------------------------------------------------+
|  models/        pydantic domain models (Event, Market,        |
|                 OrderBook, Position, OpenOrder, Profile, ...) |
+---------------------------------------------------------------+
|  core/          config, credstore, auth bootstrap, ntp, fmt   |
+---------------------------------------------------------------+
```

Dependency rule: arrows point down only. Screens reach clients/services via
attributes on the App (`app.gamma`, `app.portfolio`, `app.orders`, ...).
Services and clients return domain models, never raw JSON - the four upstream
APIs overlap and disagree on field names, and pydantic models absorb the
quirks (Gamma's JSON-encoded string lists, string numbers) at the boundary.

## Project layout

```
src/polymarket_tui/
  __main__.py            # entry point: PolymarketApp().run()
  core/
    config.py            # Settings (pydantic-settings) + capability modes
    credstore.py         # ~/.config/polymarket-tui/credentials.toml (0600)
    auth.py              # L2 cred bootstrap (V1 client -> V2 creds)
    ntp.py               # stdlib SNTP offset probe for the header clock
    fmt.py               # cents/money/size/date formatters, trunc
  models/
    market.py            # Tag, Series, Market, Event, OrderBook, PricePoint
    portfolio.py         # Position, ClosedPosition, ActivityItem, Profile, OpenOrder
  api/
    gamma.py             # async httpx: events, markets, tags, search, comments
    clob.py              # async httpx: public book + price history
    clob_auth.py         # py-clob-client-v2 behind asyncio.to_thread (auth'd)
    data.py              # async httpx: positions, trades, activity, user-pnl
  services/
    portfolio.py         # TTL-cached positions/balance/value/activity
    orders.py            # validation pipeline, place/cancel, JSONL audit
  state/
    watchlist.py         # starred events + followed traders (JSON, v1->v2)
  ui/
    app.py               # PolymarketApp: global bindings, account strip, nav
    screens/
      home.py event.py market.py portfolio.py search.py watchlist.py
      user.py related.py reader.py auth.py help.py
    widgets/
      app_header.py      # title + account strip + ms clock (20Hz)
      event_table.py     # EventsTable (shared list rows)
      preview.py         # EventsBrowser (table + cursor-following preview rail)
      book_panel.py      # order book with log-scaled size bars
      order_panel.py     # inline order entry (price/size, confirm strip)
      trades_table.py    # live trades, compact/full presets
      trader_overview.py # value + top positions for an address
      pnl_strip.py       # all-time profit chart strip (portfolio + trader profile)
      comment_list.py    # event/series comments as a cursored list (ReaderModal)
      linechart.py       # smooth box-drawing chart renderer
      price_chart.py     # legend + chart panel with crosshair inspect
      confirm_modal.py   # y/esc confirmation with arming delay
      vim_table.py       # arrow-first DataTable (TopReached/BottomReached)
      tables.py          # shared positions-table columns/rows, pnl_text
    styles/app.tcss
tests/
  test_orders.py         # table-driven validation + cancel gating
  test_credstore.py      # credentials round-trip, permissions
```

## Async model

Everything runs on Textual's single asyncio event loop.

- **REST**: `httpx.AsyncClient` per API host (HTTP/2, pooling). Screens call
  clients from `@work` Textual workers so slow calls never block rendering.
- **py-clob-client-v2 is synchronous**: every call goes through
  `asyncio.to_thread` inside `api/clob_auth.py`. The client is bootstrapped
  lazily on first authenticated call and cached.
- **Polling**: the order book refetches every 3s on market screens; the
  trades rail every 5s; balances/account strip every 60s; NTP offset every
  15min. Websocket streaming is planned (issue #1) but not built - there is
  no ws.py/stream service yet.
- **Order placement runs on an app-lifetime worker** so closing the panel
  cannot cancel an in-flight post (the HTTP request would still land).

## Data flow examples

### Viewing a market

```
MarketScreen.on_mount
  -> fill outcome table from Market metadata (Gamma fields)
  -> app.clob.order_book(token)        # snapshot now, re-poll every 3s
  -> app.clob.prices_history(token)    # chart series for the active timeframe
  -> app.data.market_trades(condition) # trades rail, re-poll every 5s
  -> app.portfolio.positions()         # "YOUR POSITION" line (cached, 30s TTL)
```

### Placing an order

```
OrderPanel (b/s) -> enter
  -> OrderService.validate(draft, book, cash, position)
       blocks mirror exchange rejections only; warnings never block
  -> confirm strip arms; y
  -> OrderService.place(draft)   # DRY: sign only; LIVE: create+post (to_thread)
  -> audit line appended to ~/.local/share/polymarket-tui/orders.jsonl
  -> toast; portfolio caches invalidated; account strip refreshed
```

## State and caching

`PortfolioService` owns the per-account caches:

| Cache | TTL / invalidation |
|---|---|
| Positions | 30s TTL, force-refreshed by the portfolio screen, invalidated on placement |
| Portfolio value / USDC balance | 60s TTL, invalidated on placement |
| Open orders / activity | fetched on demand (no cache) |

Watchlist (events + traders) persists to `~/.local/share/polymarket-tui/`.
Credentials persist via `core/credstore.py`; env vars override the file;
the LIVE flag persists alongside them (a LIVE start is announced).

## Error handling

- Workers catch client exceptions and surface toasts, never tracebacks;
  panels show "unavailable" states inline.
- Auth bootstrap failure degrades to observer/read-only rather than exiting.
- A timed-out order post reports status-unknown and is never auto-retried -
  it may have landed; check Open Orders first.

## Testing strategy

- `services/orders.py` gets the densest coverage: table-driven validation
  tests pinning the warn-only policy, plus cancel gating with a fake client.
- `core/credstore.py`: round-trip, permissions, corrupt-file handling.
- Audit writes are isolated to tmp via an autouse fixture.
- UI changes are verified by driving the real app in tmux against the live
  APIs (see CLAUDE.md) rather than mocked Pilot suites.
