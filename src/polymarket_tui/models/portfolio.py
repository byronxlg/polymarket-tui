"""Portfolio domain models (data-api and CLOB shapes)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=UTC)


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
        return float(v) if isinstance(v, str) and v else v

    @property
    def remaining(self) -> float:
        return max(0.0, self.original_size - self.size_matched)

    @property
    def when(self) -> datetime | None:
        if not self.created_at:
            return None
        return datetime.fromtimestamp(self.created_at, tz=UTC)
