"""Portfolio domain models (data-api v2, gamma and CLOB shapes)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _DataApiRow(BaseModel):
    """A row of data-api v2 (snake_case, every amount a JSON number).

    v2 documents a null numeric as "unavailable, not zero", and these fields are
    non-optional floats, so a null must fall back to the field's default rather
    than fail validation and take the whole response down with one row.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class Position(_DataApiRow):
    asset: str = Field(default="", alias="token_id")
    condition_id: str = ""
    event_slug: str = ""
    slug: str = ""
    title: str = ""
    outcome: str = ""
    outcome_index: int = 0
    size: float = Field(default=0.0, alias="current_size")
    avg_price: float = 0.0
    cur_price: float = Field(default=0.0, alias="current_price")
    initial_value: float = Field(default=0.0, alias="entry_cost_usdc")
    current_value: float = 0.0
    cash_pnl: float = Field(default=0.0, alias="unrealized_pnl")
    percent_pnl: float = 0.0
    realized_pnl: float = 0.0
    redeemable: bool = False
    end_date: datetime | None = None

    @property
    def resolved_loss(self) -> bool:
        """Losing shares of a resolved market: the book is gone and redemption
        pays 0, so data-api keeps returning them (redeemable, price 0) until
        redeemed. A 50/50 resolution prices at 0.5 and still pays - not a loss."""
        return self.redeemable and self.cur_price < 0.5


class ClosedPosition(_DataApiRow):
    """An exited position: data-api /v2/positions?status=CLOSED.

    The shares are gone (current_size is 0), so there is no current value to
    mark - the money is realized_pnl measured against what went in.

    cur_price is 1 or 0 for a position held to resolution, but a mid price for
    one sold out beforehand, so it does not mean "won". The sign of
    realized_pnl is the fact; the app states it and draws no verdict.
    """

    asset: str = Field(default="", alias="token_id")
    condition_id: str = ""
    event_slug: str = ""
    slug: str = ""
    title: str = ""
    outcome: str = ""
    outcome_index: int = 0
    avg_price: float = 0.0
    cur_price: float = Field(default=0.0, alias="current_price")
    total_size: float = 0.0  # shares ever held; current_size is 0 by now
    realized_pnl: float = 0.0
    percent_pnl: float = Field(default=0.0, alias="percent_realized_pnl")
    timestamp: int = Field(default=0, alias="last_event_at")  # when it closed
    end_date: datetime | None = None

    @property
    def total_bought(self) -> float:
        """USDC that went in: total_cost_usdc is not it, that is only the fees
        once a position has fully exited. The server's own percent_realized_pnl
        is realized_pnl over this figure."""
        return self.total_size * self.avg_price

    @property
    def closed_at(self) -> datetime | None:
        if not self.timestamp:
            return None
        return datetime.fromtimestamp(self.timestamp, tz=UTC)


class ActivityItem(_DataApiRow):
    type: str = ""
    side: str = ""
    size: float = 0.0
    usdc_size: float = 0.0
    price: float = 0.0
    outcome: str = ""
    title: str = ""
    slug: str = ""
    event_slug: str = ""
    condition_id: str = ""
    asset: str = Field(default="", alias="token_id")
    timestamp: int = 0
    name: str = ""
    pseudonym: str = ""
    proxy_wallet: str = ""

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
