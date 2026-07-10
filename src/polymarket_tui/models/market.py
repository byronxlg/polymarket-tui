"""Domain models. Gamma encodes several list fields as JSON strings; validators decode them."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _decode_json_list(v: object) -> list:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []
    return v if isinstance(v, list) else []


class Tag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str = ""
    slug: str = ""


class Series(BaseModel):
    """Recurring group an event belongs to (e.g. 'Seoul Daily Weather', daily)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    slug: str = ""
    title: str = ""
    recurrence: str = ""  # "daily", "weekly", ...


class Market(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = ""
    question: str = ""
    slug: str = ""
    condition_id: str = Field(default="", alias="conditionId")
    clob_token_ids: list[str] = Field(default_factory=list, alias="clobTokenIds")
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[str] = Field(default_factory=list, alias="outcomePrices")
    group_item_title: str = Field(default="", alias="groupItemTitle")
    group_item_threshold: float = Field(default=0.0, alias="groupItemThreshold")
    best_bid: float | None = Field(default=None, alias="bestBid")
    best_ask: float | None = Field(default=None, alias="bestAsk")
    spread: float | None = None
    one_day_price_change: float | None = Field(default=None, alias="oneDayPriceChange")
    volume_24hr: float | None = Field(default=None, alias="volume24hr")
    liquidity: float | None = None
    end_date: datetime | None = Field(default=None, alias="endDate")
    active: bool = True
    closed: bool = False
    # When trading actually halted. Gamma sends postgres-style timestamps
    # ("2024-11-06 15:17:41+00") that pydantic rejects; see _pg_datetime.
    closed_time: datetime | None = Field(default=None, alias="closedTime")
    # UMA oracle state; null until a resolution is proposed, "resolved" once
    # final. Every closed market observed carries "resolved".
    uma_resolution_status: str | None = Field(default=None, alias="umaResolutionStatus")
    # CLOB order gate. Independent of end_date: markets awaiting resolution
    # (e.g. yesterday's weather) keep accepting orders past endDate.
    accepting_orders: bool = Field(default=True, alias="acceptingOrders")
    description: str = ""
    order_price_min_tick_size: float | None = Field(default=None, alias="orderPriceMinTickSize")
    order_min_size: float | None = Field(default=None, alias="orderMinSize")
    raw_events: list = Field(default_factory=list, alias="events")

    @property
    def event_slug(self) -> str | None:
        """Slug of the parent event when Gamma embeds it (markets fetched directly)."""
        for entry in self.raw_events:
            if isinstance(entry, dict) and entry.get("slug"):
                return str(entry["slug"])
        return None

    _decode_tokens = field_validator("clob_token_ids", "outcomes", "outcome_prices", mode="before")(
        _decode_json_list
    )

    @field_validator("closed_time", mode="before")
    @classmethod
    def _pg_datetime(cls, v: object) -> object:
        # Gamma's closedTime ends in a bare "+00" offset, which pydantic's
        # ISO parser rejects - pad it to "+00:00".
        if isinstance(v, str) and re.search(r"[+-]\d{2}$", v):
            return v + ":00"
        return v

    @field_validator("liquidity", "volume_24hr", mode="before")
    @classmethod
    def _num_str(cls, v: object) -> object:
        # ""/garbage must become None, not be left for float coercion to choke
        # on - one malformed market would reject the whole events payload.
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return None
        return v

    @field_validator("group_item_threshold", mode="before")
    @classmethod
    def _num_str_zero(cls, v: object) -> object:
        # Non-optional (sort key): ""/garbage degrades to 0.0, not None.
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return 0.0
        return v

    @property
    def display_title(self) -> str:
        return self.group_item_title or self.question

    @property
    def yes_price(self) -> float | None:
        """Mid-ish YES price: prefer outcomePrices[0], fall back to bid/ask mid."""
        if self.outcome_prices:
            try:
                return float(self.outcome_prices[0])
            except (ValueError, IndexError):
                pass
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def winning_outcome(self) -> str | None:
        """Resolved winner, read from the frozen outcomePrices (1/0 after
        resolution). None while trading or when prices aren't decisive."""
        if not self.closed or not self.outcomes:
            return None
        try:
            prices = [float(p) for p in self.outcome_prices]
        except ValueError:
            return None
        if len(prices) != len(self.outcomes) or not prices:
            return None
        best = max(range(len(prices)), key=lambda i: prices[i])
        return self.outcomes[best] if prices[best] > 0.5 else None

    def token_id(self, outcome_index: int) -> str | None:
        try:
            return self.clob_token_ids[outcome_index]
        except IndexError:
            return None


class Event(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = ""
    slug: str = ""
    title: str = ""
    description: str = ""
    end_date: datetime | None = Field(default=None, alias="endDate")
    volume_24hr: float | None = Field(default=None, alias="volume24hr")
    liquidity: float | None = None
    sort_by: str | None = Field(default=None, alias="sortBy")
    tags: list[Tag] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    markets: list[Market] = Field(default_factory=list)
    closed: bool = False

    @field_validator("liquidity", "volume_24hr", mode="before")
    @classmethod
    def _num_str(cls, v: object) -> object:
        # See Market._num_str: ""/garbage degrades to None, not a model failure.
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return None
        return v

    @property
    def active_markets(self) -> list[Market]:
        """Markets in display order.

        Gamma's `sortBy` says how the web UI orders an event's markets:
        "price" -> highest chance first; anything else -> the market-defined
        `groupItemThreshold` order (range events like temperature/price bands
        define it ascending).

        Closed markets are hidden while the event trades, but once none are
        left (resolved event, reached via search/related) the closed ones are
        the content - without them the event drills into an empty screen.
        The winner sorts first under the price rule (its price froze at 1).
        """
        ms = [m for m in self.markets if m.active and not m.closed]
        if not ms:
            ms = [m for m in self.markets if m.active]
        if self.sort_by == "price":
            return sorted(ms, key=lambda m: m.yes_price or 0, reverse=True)
        return sorted(ms, key=lambda m: m.group_item_threshold)

    @property
    def top_market(self) -> Market | None:
        """Highest-priced market regardless of display order (for browse lists)."""
        ms = self.active_markets
        return max(ms, key=lambda m: m.yes_price or 0) if ms else None

    @property
    def is_binary(self) -> bool:
        return len(self.active_markets) == 1

    @property
    def primary_series(self) -> Series | None:
        return self.series[0] if self.series else None

    _META_TAGS = frozenset({"hide from new", "recurring", "trending", "all"})

    @property
    def most_specific_tag(self) -> Tag | None:
        """Best tag for finding related events; Gamma orders broad -> specific."""
        for tag in reversed(self.tags):
            if tag.label.lower() not in self._META_TAGS and tag.slug:
                return tag
        return None


class BookLevel(BaseModel):
    price: float
    size: float

    @field_validator("price", "size", mode="before")
    @classmethod
    def _num(cls, v: object) -> float:
        return float(v)


class OrderBook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)
    # The exchange's tick for this token, sent as a string ("0.001") on every
    # REST /book and every ws `book` frame. This is the only live authority:
    # the CLOB changes a market's tick as its price moves and announces it with
    # `tick_size_change`. Gamma's orderPriceMinTickSize mirrors it but is
    # snapshotted when the pane opens, so it goes stale. None until a book
    # arrives (a locally-built book, or one from before this field existed).
    tick_size: Decimal | None = None

    @property
    def best_bid(self) -> BookLevel | None:
        return max(self.bids, key=lambda lvl: lvl.price) if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return min(self.asks, key=lambda lvl: lvl.price) if self.asks else None

    @property
    def midpoint(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        if bb and ba:
            return (bb.price + ba.price) / 2
        return None

    @property
    def spread(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        if bb and ba:
            return ba.price - bb.price
        return None


class PricePoint(BaseModel):
    t: int
    p: float

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.t, tz=UTC)
