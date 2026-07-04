"""Credential persistence: TOML at ~/.config/polymarket-tui/, mode 0600.

Everything lives in the plaintext TOML (0600, outside any git working tree).
The macOS Keychain backend (issue #5) was retired 2026-07-05: reading the key
triggered a per-run "allow" popup because each venv python counts as a new
binary, so the key moved back to the file; a legacy Keychain entry is migrated
into the TOML (and deleted) on first load. The execution-live flag is
persisted here too: a session starts in the mode you left it in, and the app
announces a LIVE start loudly.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from polymarket_tui.core import keychain

CONFIG_DIR = Path.home() / ".config" / "polymarket-tui"
CRED_PATH = CONFIG_DIR / "credentials.toml"


def key_backend() -> str:
    """The private key lives in the TOML (Keychain retired - per-run popups)."""
    return "file"


def _write_toml(
    funder: str, signature_type: int, private_key: str = "", execution_live: bool = False
) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    lines = [
        "# polymarket-tui credentials - plaintext, keep permissions 0600.",
    ]
    lines.append(f'funder = "{funder}"')
    if private_key:
        lines.append(f'private_key = "{private_key}"')
    lines.append(f"signature_type = {signature_type}")
    lines.append(f"execution_live = {str(execution_live).lower()}")
    body = "\n".join(lines) + "\n"
    # Create with restrictive permissions before writing any secret.
    fd = os.open(CRED_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(body)
    CRED_PATH.chmod(0o600)
    return CRED_PATH


def load_credentials() -> dict | None:
    """Return {funder, private_key, signature_type} or None if absent/unreadable.

    Migrates a key still sitting in the TOML into the Keychain on first read.
    """
    try:
        with CRED_PATH.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    funder = str(data.get("funder", ""))
    signature_type = int(data.get("signature_type", 1))
    file_key = str(data.get("private_key", ""))

    # Reverse migration: a key still in the legacy Keychain entry moves back
    # into the TOML (one last "allow" popup) and the entry is deleted, so
    # later runs never touch the Keychain.
    private_key = file_key
    if not private_key and keychain.available():
        legacy = keychain.get_key() or ""
        if legacy:
            _write_toml(
                funder,
                signature_type,
                private_key=legacy,
                execution_live=bool(data.get("execution_live", False)),
            )
            keychain.delete_key()
            private_key = legacy

    return {
        "funder": funder,
        "private_key": private_key,
        "signature_type": signature_type,
        "execution_live": bool(data.get("execution_live", False)),
    }


def save_credentials(
    funder: str, private_key: str, signature_type: int, execution_live: bool = False
) -> Path:
    """Persist credentials to the TOML (0600)."""
    return _write_toml(
        funder, signature_type, private_key=private_key, execution_live=execution_live
    )


def save_execution_live(live: bool) -> Path | None:
    """Persist just the execution mode, keeping the stored credentials as-is.
    No-op (returns None) when no credentials file exists yet."""
    saved = load_credentials()
    if saved is None:
        return None
    return save_credentials(
        saved["funder"], saved["private_key"], saved["signature_type"], execution_live=live
    )


def clear_credentials() -> bool:
    """Delete the TOML and any Keychain entry. True if either existed."""
    removed_key = keychain.delete_key()
    try:
        CRED_PATH.unlink()
        removed_file = True
    except FileNotFoundError:
        removed_file = False
    return removed_key or removed_file
