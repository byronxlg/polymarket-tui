"""Credential persistence: plaintext TOML at ~/.config/polymarket-tui/, mode 0600.

Deliberately outside any git working tree. The execution-live flag is never
persisted - every session starts in dry-run.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "polymarket-tui"
CRED_PATH = CONFIG_DIR / "credentials.toml"


def load_credentials() -> dict | None:
    """Return {funder, private_key, signature_type} or None if absent/unreadable."""
    try:
        with CRED_PATH.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "funder": str(data.get("funder", "")),
        "private_key": str(data.get("private_key", "")),
        "signature_type": int(data.get("signature_type", 1)),
    }


def save_credentials(funder: str, private_key: str, signature_type: int) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    body = (
        "# polymarket-tui credentials - plaintext, keep permissions 0600.\n"
        "# execution mode (dry/live) is intentionally not stored here.\n"
        f'funder = "{funder}"\n'
        f'private_key = "{private_key}"\n'
        f"signature_type = {signature_type}\n"
    )
    # Create with restrictive permissions before writing the secret.
    fd = os.open(CRED_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(body)
    CRED_PATH.chmod(0o600)
    return CRED_PATH


def clear_credentials() -> bool:
    """Delete the credentials file. Returns True if one existed."""
    try:
        CRED_PATH.unlink()
        return True
    except FileNotFoundError:
        return False
