"""Portfolio domain models (data-api and CLOB shapes)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Position(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    asset: str = ""  # token id
    condition_id: str = Field(default="", alias="conditionId")
    event_slug: str = Field(default="", alias="eventSlug")
    slug: str = ""
    title: str = ""
    outcome: str = ""
    outcome_index: int = Field(default=0, alias="outcomeIndex")
    size: float = 0.0
    avg_price: float = Field(default=0.0, alias="avgPrice")
    cur_price: float = Field(default=0.0, alias="curPrice")
    initial_value: float = Field(default=0.0, alias="initialValue")
    current_value: float = Field(default=0.0, alias="currentValue")
    cash_pnl: float = Field(default=0.0, alias="cashPnl")
    percent_pnl: float = Field(default=0.0, alias="percentPnl")
    realized_pnl: float = Field(default=0.0, alias="realizedPnl")
    redeemable: bool = False
    end_date: datetime | None = Field(default=None, alias="endDate")

    @property
    def resolved_loss(self) -> bool:
        """Losing shares of a resolved market: the book is gone and redemption
        pays 0, so data-api keeps returning them (redeemable, price 0) until
        redeemed. A 50/50 resolution prices at 0.5 and still pays - not a loss."""
        return self.redeemable and self.cur_price < 0.5


class ActivityItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    type: str = ""
    side: str = ""
    size: float = 0.0
    usdc_size: float = Field(default=0.0, alias="usdcSize")
    price: float = 0.0
    outcome: str = ""
    title: str = ""
    slug: str = ""
    event_slug: str = Field(default="", alias="eventSlug")
    condition_id: str = Field(default="", alias="conditionId")
    asset: str = ""
    timestamp: int = 0
    name: str = ""
    pseudonym: str = ""
    proxy_wallet: str = Field(default="", alias="proxyWallet")

    @model_validator(mode="after")
    def _derive_usdc(self) -> ActivityItem:
        # The live trade feed omits usdcSize; notional is size * price.
        if not self.usdc_size and self.size and self.price:
            self.usdc_size = self.size * self.price
        return self

    @property
    def trader(self) -> str:
        return self.name or self.pseudonym or "anon"

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=UTC)


class Profile(BaseModel):
    """Public trader profile from gamma public-search."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = ""
    pseudonym: str = ""
    proxy_wallet: str = Field(default="", alias="proxyWallet")
    bio: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.pseudonym or self.proxy_wallet[:10]


class OpenOrder(BaseModel):
    """Shape of py-clob-client-v2 get_open_orders entries (dicts)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = ""
    asset_id: str = ""
    market: str = ""  # condition id
    side: str = ""
    price: float = 0.0
    original_size: float = Field(default=0.0, alias="original_size")
    size_matched: float = Field(default=0.0, alias="size_matched")
    outcome: str = ""
    created_at: int = 0

    @field_validator("price", "original_size", "size_matched", mode="before")
    @classmethod
    def _num(cls, v: object) -> object:
        # ""/garbage degrades to 0.0 (fields are non-optional) rather than
        # failing the model and dropping the whole open-orders response.
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return 0.0
        return v

    @property
    def remaining(self) -> float:
        return max(0.0, self.original_size - self.size_matched)

    @property
    def when(self) -> datetime | None:
        if not self.created_at:
            return None
        return datetime.fromtimestamp(self.created_at, tz=UTC)
