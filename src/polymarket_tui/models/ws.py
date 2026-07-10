"""CLOB market-channel websocket frames and live book maintenance (issue #1).

Shapes verified by capturing real frames from
wss://ws-subscriptions-clob.polymarket.com/ws/market (see tests/fixtures/ws_market_*).
Frames arrive batched as a JSON array. Note the real `price_change` shape differs
from prior docs: it carries `price_changes` (plural), each entry with its own
`asset_id`, `side`, `price`, `size`, and `best_bid`/`best_ask`.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from polymarket_tui.models.market import BookLevel, OrderBook


class WsLevel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    price: str
    size: str


class BookMessage(BaseModel):
    """`book` - full snapshot for one asset."""

    model_config = ConfigDict(extra="ignore")
    event_type: str = "book"
    asset_id: str = ""
    market: str = ""
    bids: list[WsLevel] = Field(default_factory=list)
    asks: list[WsLevel] = Field(default_factory=list)
    tick_size: Decimal | None = None  # the exchange's current tick, e.g. "0.001"
    timestamp: int = 0


class PriceChange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    asset_id: str = ""
    price: str = ""
    size: str = ""  # new absolute level size; "0" removes the level
    side: str = ""  # BUY -> bid, SELL -> ask
    best_bid: str = ""
    best_ask: str = ""


class PriceChangeMessage(BaseModel):
    """`price_change` - level deltas, possibly across several assets in one market."""

    model_config = ConfigDict(extra="ignore")
    event_type: str = "price_change"
    market: str = ""
    price_changes: list[PriceChange] = Field(default_factory=list)
    timestamp: int = 0


class LastTradeMessage(BaseModel):
    """`last_trade_price` - a trade print."""

    model_config = ConfigDict(extra="ignore")
    event_type: str = "last_trade_price"
    asset_id: str = ""
    price: str = ""
    size: str = ""
    side: str = ""
    timestamp: int = 0


class TickSizeChangeMessage(BaseModel):
    """`tick_size_change` - the exchange re-priced this token's tick grid.

    Emitted as a market's price approaches 0 or 1, where the CLOB switches to a
    finer tick (typically 0.01 -> 0.001). Acting on this is what keeps the book
    and the order form at the exchange's real resolution: Gamma's
    orderPriceMinTickSize only catches up on the next fetch, and a pane holds
    its Market snapshot for its whole life.
    """

    model_config = ConfigDict(extra="ignore")
    event_type: str = "tick_size_change"
    asset_id: str = ""
    market: str = ""
    old_tick_size: Decimal | None = None
    new_tick_size: Decimal | None = None
    timestamp: int = 0


_TYPES = {
    "book": BookMessage,
    "price_change": PriceChangeMessage,
    "last_trade_price": LastTradeMessage,
    "tick_size_change": TickSizeChangeMessage,
}

MarketMessage = BookMessage | PriceChangeMessage | LastTradeMessage | TickSizeChangeMessage


def parse_market_message(raw: dict) -> MarketMessage | None:
    """Type one frame by its event_type. Returns None for unknown types."""
    model = _TYPES.get(raw.get("event_type", ""))
    return model.model_validate(raw) if model else None


# -- user channel (/ws/user) --------------------------------------------------
# Shapes verified from real captured frames (see tests/fixtures/ws_user_*).


class UserOrderMessage(BaseModel):
    """`order` - own order lifecycle. type is PLACEMENT/UPDATE/CANCELLATION;
    status is LIVE/MATCHED/CANCELED. size_matched grows as the order fills."""

    model_config = ConfigDict(extra="ignore")
    event_type: str = "order"
    id: str = ""
    market: str = ""  # condition id
    asset_id: str = ""
    side: str = ""
    outcome: str = ""
    price: str = ""
    original_size: str = ""
    size_matched: str = "0"
    type: str = ""  # PLACEMENT | UPDATE | CANCELLATION
    status: str = ""  # LIVE | MATCHED | CANCELED
    timestamp: int = 0

    @property
    def resting(self) -> bool:
        """Still (partly) on the book: a LIVE order not fully matched."""
        return self.status == "LIVE"

    @property
    def gone(self) -> bool:
        """No longer on the book (cancelled or fully matched)."""
        return self.status in ("CANCELED", "MATCHED")


class UserTradeMessage(BaseModel):
    """`trade` - own fill. status walks MATCHED -> MINED -> CONFIRMED."""

    model_config = ConfigDict(extra="ignore")
    event_type: str = "trade"
    id: str = ""
    market: str = ""
    asset_id: str = ""
    side: str = ""
    outcome: str = ""
    price: str = ""
    size: str = ""
    status: str = ""
    timestamp: int = 0


_USER_TYPES = {"order": UserOrderMessage, "trade": UserTradeMessage}


def parse_user_message(raw: dict) -> UserOrderMessage | UserTradeMessage | None:
    model = _USER_TYPES.get(raw.get("event_type", ""))
    return model.model_validate(raw) if model else None


class LiveBook:
    """One asset's book, maintained from a `book` snapshot plus `price_change`
    deltas. Frames strictly older than the last applied timestamp are discarded.
    """

    def __init__(self) -> None:
        self._bids: dict[str, float] = {}  # price string -> size
        self._asks: dict[str, float] = {}
        self._ts: int = 0
        # Survives price_change deltas (which never carry it) and outlives any
        # single snapshot, so the book always renders at the exchange's tick.
        self._tick: Decimal | None = None
        self.applied: int = 0  # frames applied, for staleness/debug

    def apply_book(self, msg: BookMessage) -> bool:
        if msg.timestamp and msg.timestamp < self._ts:
            return False
        self._bids = {lvl.price: float(lvl.size) for lvl in msg.bids if float(lvl.size) > 0}
        self._asks = {lvl.price: float(lvl.size) for lvl in msg.asks if float(lvl.size) > 0}
        self._ts = msg.timestamp or self._ts
        if msg.tick_size:
            self._tick = msg.tick_size
        self.applied += 1
        return True

    def apply_tick_size(self, msg: TickSizeChangeMessage) -> bool:
        """Adopt a new tick. Returns True when it actually moved, so the channel
        only wakes the UI on a real change (the CLOB repeats the frame)."""
        if not msg.new_tick_size or msg.new_tick_size == self._tick:
            return False
        self._tick = msg.new_tick_size
        return True

    def apply_price_change(self, msg: PriceChangeMessage, asset_id: str) -> bool:
        if msg.timestamp and msg.timestamp < self._ts:
            return False
        touched = False
        for change in msg.price_changes:
            if change.asset_id != asset_id:
                continue
            book = self._bids if change.side == "BUY" else self._asks
            size = float(change.size or 0)
            if size <= 0:
                book.pop(change.price, None)
            else:
                book[change.price] = size
            touched = True
        if touched:
            self._ts = max(self._ts, msg.timestamp)
            self.applied += 1
        return touched

    def order_book(self) -> OrderBook:
        return OrderBook(
            bids=[BookLevel(price=float(p), size=s) for p, s in self._bids.items()],
            asks=[BookLevel(price=float(p), size=s) for p, s in self._asks.items()],
            tick_size=self._tick,
        )
