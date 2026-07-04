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


# The builder code shipped with the app (Polymarket Builders Program, issue #12).
# Public, not a secret - it is an on-chain identifier, so hardcoding it here is
# safe and deliberate: every install attributes its fills to us BY DEFAULT, which
# is the only way to get attribution from other people running the TUI (the code
# must be present in whatever instance signs the order). Users keep full control:
# POLYMARKET_BUILDER_CODE (or credentials.toml) overrides this to self-attribute,
# and an explicit "off" value (see _BUILDER_CODE_OFF) disables attribution.
DEFAULT_BUILDER_CODE = "0x97fe407b11c95484a98264376f8bbd2152c7375d69eff687b914c3d1eff38ede"

# Override values a user can set to opt out of attribution entirely.
_BUILDER_CODE_OFF = frozenset({"0", "off", "none", "false", "0x0", "0x" + "0" * 64})


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
        """Builder code to attribute orders with, or None for no attribution.

        Resolution: no override -> the shipped DEFAULT_BUILDER_CODE (so every
        install attributes by default); an explicit off value -> None; anything
        else -> the validated override, or None if malformed.
        """
        raw = self.polymarket_builder_code.strip().lower()
        if not raw:
            return DEFAULT_BUILDER_CODE
        if raw in _BUILDER_CODE_OFF:
            return None
        return normalize_builder_code(raw)

    @property
    def builder_code_is_misconfigured(self) -> bool:
        """True when a non-empty override is neither valid nor a known 'off' value."""
        raw = self.polymarket_builder_code.strip().lower()
        return bool(raw) and raw not in _BUILDER_CODE_OFF and normalize_builder_code(raw) is None

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
