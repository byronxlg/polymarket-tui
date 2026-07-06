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

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    READ_ONLY = "RO"
    OBSERVER = "OBS"
    TRADER_DRY = "DRY"
    TRADER_LIVE = "LIVE"


# The builder code every order is attributed to (Polymarket Builders Program,
# issue #12). Hardcoded on purpose and NOT configurable: attribution is stamped
# client-side at signing time, so the only way to get attributed for orders placed
# by other people running the TUI is to bake the code into the app itself. There is
# deliberately no env var or config override - an override would just hand every
# user a switch to redirect attribution away from us. The code is public (an
# on-chain identifier), not a secret, so hardcoding it here is safe. Attribution can
# only be removed by editing this constant in source (open source, so unavoidable;
# only server-side signing could truly enforce it).
BUILDER_CODE = "0x97fe407b11c95484a98264376f8bbd2152c7375d69eff687b914c3d1eff38ede"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    polymarket_private_key: str = ""
    polymarket_funder: str = ""
    polymarket_signature_type: int = 1
    polymarket_execution_live: bool = False
    polymarket_host: str = "https://clob.polymarket.com"
    pmtui_max_notional: float = 500.0
    # Streamer/demo mode: mask the account numbers that would otherwise be
    # on screen (header cash/pf, the market screen's YOUR POSITION strip,
    # the order panel's held hint). Used when screen-sharing and by
    # scripts/record_demo.sh so the public landing-page cast never carries
    # real balances. Trading behavior is unchanged.
    polymarket_hide_balances: bool = False

    @field_validator(
        "polymarket_signature_type",
        "polymarket_execution_live",
        "pmtui_max_notional",
        "polymarket_hide_balances",
        mode="before",
    )
    @classmethod
    def _empty_env_is_unset(cls, v: object, info) -> object:
        # `export POLYMARKET_SIGNATURE_TYPE=` (a common profile shape) must
        # mean "unset", not a ValidationError that kills the app at launch.
        if isinstance(v, str) and not v.strip():
            return cls.model_fields[info.field_name].default
        return v

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
            # Persisted execution mode (env still wins via the early return
            # above when env credentials are set).
            "polymarket_execution_live": settings.polymarket_execution_live
            or saved.get("execution_live", False),
        }
    )
