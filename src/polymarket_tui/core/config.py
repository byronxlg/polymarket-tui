"""Settings and capability-mode detection.

Modes (config-and-auth.md):
  read-only  - no creds: browse, books, charts, watchlist
  observer   - POLYMARKET_FUNDER only: + positions, P&L, activity (data-api is public)
  trader-dry - key + funder: + balance, open orders, full order pipeline, logged dry-run
  trader-live- trader-dry + POLYMARKET_EXECUTION_LIVE=1: real order posting
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    READ_ONLY = "RO"
    OBSERVER = "OBS"
    TRADER_DRY = "DRY"
    TRADER_LIVE = "LIVE"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    polymarket_private_key: str = ""
    polymarket_funder: str = ""
    polymarket_signature_type: int = 1
    polymarket_execution_live: bool = False
    polymarket_host: str = "https://clob.polymarket.com"
    pmtui_max_notional: float = 500.0

    @property
    def mode(self) -> Mode:
        if self.polymarket_private_key and self.polymarket_funder:
            return Mode.TRADER_LIVE if self.polymarket_execution_live else Mode.TRADER_DRY
        if self.polymarket_funder:
            return Mode.OBSERVER
        return Mode.READ_ONLY

    @property
    def can_read_portfolio(self) -> bool:
        return bool(self.polymarket_funder)

    @property
    def can_auth(self) -> bool:
        return self.mode in (Mode.TRADER_DRY, Mode.TRADER_LIVE)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Env vars win; otherwise fall back to the saved credentials file."""
    from polymarket_tui.core.credstore import load_credentials

    settings = Settings()
    if settings.polymarket_private_key or settings.polymarket_funder:
        return settings
    saved = load_credentials()
    if saved is None:
        return settings
    return settings.model_copy(
        update={
            "polymarket_funder": saved["funder"],
            "polymarket_private_key": saved["private_key"],
            "polymarket_signature_type": saved["signature_type"],
        }
    )
