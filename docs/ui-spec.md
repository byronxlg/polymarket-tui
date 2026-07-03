# UI specification

Textual app, dark theme default, mouse supported but fully keyboard-drivable.
Design language: dense tables, vim-ish navigation, single persistent header/footer.

## Global chrome

```
+----------------------------------------------------------------------------+
| polymarket-tui   [Trending] Politics Sports Crypto Economy Tech  | $9.49   |  <- header: tag bar + portfolio value / cash
+----------------------------------------------------------------------------+
|                                                                            |
|                             <active screen>                                |
|                                                                            |
+----------------------------------------------------------------------------+
| j/k move  enter open  / search  p portfolio  w watchlist  ? help  q quit   |  <- footer: context bindings
+----------------------------------------------------------------------------+
```

Header right side: `cash: $123.45 | value: $9.49 | RO` (RO badge in read-only mode;
stale badge when WS is down and data is poll-based).

## Global keybindings

| Key | Action |
|---|---|
| `/` | search screen |
| `h` or `escape` | back (screen stack pop) |
| `H` | home |
| `p` | portfolio |
| `w` | watchlist |
| `a` | activity |
| `?` | help screen (all bindings) |
| `r` | refresh current screen |
| `q` | quit (confirm if open orders were placed this session) |
| `1-9` | jump to tag N in tag bar |
| `[` `]` | prev/next tag |

Table navigation everywhere: `j/k` or arrows to move, `g/G` top/bottom, `ctrl+d/u`
half-page, `enter` to open.

## Screens

Screen stack model: Home is the root; Event, Market push onto the stack; escape pops.
Portfolio/Watchlist/Activity/Search are siblings reachable from anywhere.

### 1. Home / browse  (`screens/home.py`)

The web UI's front page: event cards -> here an event table.

```
| # | Event                                | Top outcome        | 24h vol | Ends   | d24h  |
|---|--------------------------------------|--------------------|---------|--------|-------|
| 1 | World Cup Winner                     | Spain 12c          | $5.0M   | Jul 19 | +2.3c |
| 2 | Fed decision in July                 | No change 97c      | $2.1M   | Jul 29 | +0.4c |
```

- Data: Gamma `/events?active=true&closed=false&order=volume24hr&ascending=false&limit=50`,
  tag filter from the header tag bar (`tag_slug`).
- "Top outcome": highest-priced market's `groupItemTitle`/question short form + YES price.
  Single-market events show `Yes 97c`.
- Sort cycling on `o`: volume24hr -> liquidity -> endDate (soonest) -> newest.
- `enter` opens Event screen (or Market screen directly if the event has 1 market).
- `W` toggles watchlist membership on the highlighted row.
- Infinite scroll: fetch next `offset` page when cursor nears the bottom.

### 2. Event screen  (`screens/event.py`)

For multi-market events (elections, tournaments).

```
World Cup Winner                                     ends Jul 19 | vol24h $5.0M
Tags: Sports / FIFA World Cup

| Outcome     | Price | 24h   | Bid   | Ask   | Spread | Vol 24h |
|-------------|-------|-------|-------|-------|--------|---------|
| Spain       | 12.3c | +2.3c | 12.2c | 12.3c | 0.1c   | $5.0M   |
| France      | 11.1c | -0.5c | 11.0c | 11.2c | 0.2c   | $3.2M   |
```

- Data: Gamma `/events/{slug}`; prices come from embedded market fields (`bestBid`,
  `bestAsk`, `outcomePrices`, `oneDayPriceChange`) - no CLOB calls needed for the table.
- Sorted by price desc. `enter` opens the Market screen for that outcome.
- Description panel toggled with `i` (markdown-rendered market description/rules).

### 3. Market screen  (`screens/market.py`)

The core screen - the web UI's market page with order book, chart, trades, order entry.

```
Will Spain win the 2026 FIFA World Cup?          YES 12.3c / NO 87.7c   ends Jul 19
+------------------------------+  +------------------------------------------+
|  Price chart (YES)           |  |        ORDER BOOK (YES)         [Y/N]    |
|  1H 6H 1D 1W 1M ALL          |  |   ask 12.6   1,200 |####                 |
|      .plotext line chart.    |  |   ask 12.5   3,400 |###########          |
|                              |  |   ask 12.3     900 |##                   |
|                              |  |   --- spread 0.1c / mid 12.25 ---        |
|                              |  |   bid 12.2   2,100 |######               |
|                              |  |   bid 12.1   5,000 |################     |
|                              |  |   bid 12.0   1,000 |###                  |
+------------------------------+  +------------------------------------------+
+------------------------------+  +------------------------------------------+
| RECENT TRADES                |  | ORDER ENTRY                              |
| 12:01:03  BUY  500 @ 12.3    |  | Side: [BUY] SELL    Outcome: [YES] NO    |
| 12:00:41  SELL 200 @ 12.2    |  | Type: [LIMIT] MARKET   TIF: [GTC] ...    |
|                              |  | Price: 0.123   Size: 100   Cost: $12.30  |
| your position: 50 @ 11.0     |  | To win: $100.00        [ Review order ]  |
+------------------------------+  +------------------------------------------+
```

- Book: initial REST snapshot, then WS `book`/`price_change`. Top 8 levels per side,
  cumulative-size bars, spread/midpoint row between. `t` toggles YES/NO book.
- Chart: `prices-history` for the selected interval; keys `1..6` switch interval;
  WS `last_trade_price` appends live points. plotext line chart, YES price 0-100c axis.
- Recent trades: WS `last_trade_price` ring buffer (last 50); seeded from data-api
  `/trades?market=` if available.
- Position strip: if the user holds this market, shows size/avg/P&L (from PortfolioService).
- Order entry: `b`/`s` focus the form pre-set to BUY/SELL; full spec in trading.md.
  Hidden in read-only mode (banner instead).
- `W` watchlist toggle, `o` jump to open orders on this market (portfolio screen filtered).

### 4. Portfolio  (`screens/portfolio.py`)

Tabs (`tab`/`shift+tab` or `P/O/T` keys): Positions | Open orders | History.

Positions tab (data-api `/positions`):

```
cash $123.45   positions $9.49   total $132.94
| Market                    | Outcome | Size | Avg   | Cur   | Value | P&L        |
|---------------------------|---------|------|-------|-------|-------|------------|
| Spain WC Winner           | Yes     | 50   | 11.0c | 12.3c | $6.15 | +$0.65 +12%|
```

- Red/green P&L, `redeemable` rows flagged with `[resolved - redeem on web]`.
- `enter` opens the market screen; `s` pre-fills a SELL of the full position.

Open orders tab (CLOB `get_open_orders`, live via user WS):

```
| Market            | Side | Outcome | Price | Size | Filled | Placed   |
```

- `x` cancel highlighted (confirm modal), `X` cancel all (typed confirmation "cancel all").

History tab: CLOB `get_trades()` merged with data-api activity, newest first.

### 5. Watchlist  (`screens/watchlist.py`)

Same table as Home but sourced from persisted slugs; refreshed via
`/events?slug=a&slug=b...` (batch - verify) or per-slug fetches. Empty state explains `W`.

### 6. Search  (`screens/search.py`)

`/` from anywhere. Input at top, debounced 300ms, Gamma `/public-search`.
Results grouped: Events, then Markets. `enter` navigates.

### 7. Activity  (`screens/activity.py`)

data-api `/activity?user=` - own trades/redeems/rewards, newest first, relative times.

### 8. Help  (`screens/help.py`)

Static bindings table + version + endpoints status (WS connected? auth mode?).

## Widgets (reusable)

| Widget | Notes |
|---|---|
| `EventTable` | DataTable subclass: sort cycling, watchlist stars, infinite scroll |
| `BookWidget` | custom render; bar sizing normalized to max visible level; flashes changed levels |
| `PriceChart` | textual-plotext; interval selector; handles sparse history |
| `OrderForm` | see trading.md; validating inputs, live cost/payout math |
| `ConfirmModal` | order review; also used for cancels and quit-confirm |
| `Toast` | success/error notifications, 4s auto-dismiss, error toasts sticky |
| `TagBar` | header categories from `/tags`, number-key accelerators |
| `BalanceBar` | header stats; polls balance 30s, portfolio value 60s |

## Color/formatting conventions

- Prices displayed in cents: `12.3c` (matches web UI); inputs accept `0.123`, `12.3c`, or `12.3`.
  Internal representation is always decimal dollars (`Decimal`), never floats, for order math.
- Green = YES/buy/positive P&L; red = NO/sell/negative. Volume compacted (`$5.0M`).
- Times: relative under 24h (`3h ago`), else `Jul 19`.
- Stale data (WS down): dim the book + `stale` badge rather than hiding.

## Read-only mode

No creds -> everything works except: order entry (replaced by "read-only - set
POLYMARKET_PRIVATE_KEY to trade"), portfolio positions/activity still work if
`POLYMARKET_FUNDER` alone is set (data-api is public), balance/open-orders hidden.
