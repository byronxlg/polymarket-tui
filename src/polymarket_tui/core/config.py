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


def normalize_builder_code(raw: str) -> str | None:
    """Canonicalize a Builders-Program builder code, or None if unusable.

    A builder code is a 0x-prefixed 32-byte hex string (bytes32) attached to
    orders so matched fills are attributed on-chain. The all-zero code means
    "no attribution" and is treated the same as absent. A malformed code is
    dropped (returns None) rather than attached - a bad code counts for nobody
    and must never block or corrupt an otherwise-valid order.
    """
    raw = (raw or "").strip().lower()
    if not raw:
        return None
    if not raw.startswith("0x"):
        raw = "0x" + raw
    body = raw[2:]
    if len(body) != 64 or any(c not in "0123456789abcdef" for c in body):
        return None
    if int(body, 16) == 0:
        return None
    return raw


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    polymarket_private_key: str = ""
    polymarket_funder: str = ""
    polymarket_signature_type: int = 1
    polymarket_execution_live: bool = False
    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_builder_code: str = ""
    pmtui_max_notional: float = 500.0

    @property
    def builder_code(self) -> str | None:
        """Validated builder code to attribute orders with, or None if unset/bad."""
        return normalize_builder_code(self.polymarket_builder_code)

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
    update = {
        "polymarket_funder": saved["funder"],
        "polymarket_private_key": saved["private_key"],
        "polymarket_signature_type": saved["signature_type"],
    }
    # Env (already on `settings`) wins over the file for the builder code too.
    if not settings.polymarket_builder_code and saved.get("builder_code"):
        update["polymarket_builder_code"] = saved["builder_code"]
    return settings.model_copy(update=update)
