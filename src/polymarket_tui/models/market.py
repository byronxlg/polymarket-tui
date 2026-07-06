"""Domain models. Gamma encodes several list fields as JSON strings; validators decode them."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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

    @field_validator("liquidity", "volume_24hr", "group_item_threshold", mode="before")
    @classmethod
    def _num_str(cls, v: object) -> object:
        return float(v) if isinstance(v, str) and v else v

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
        return float(v) if isinstance(v, str) and v else v

    @property
    def active_markets(self) -> list[Market]:
        """Markets in display order.

        Gamma's `sortBy` says how the web UI orders an event's markets:
        "price" -> highest chance first; anything else -> the market-defined
        `groupItemThreshold` order (range events like temperature/price bands
        define it ascending).
        """
        ms = [m for m in self.markets if m.active and not m.closed]
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
