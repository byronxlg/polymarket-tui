"""Credential persistence: TOML at ~/.config/polymarket-tui/, mode 0600.

The private key is stored in the macOS Keychain when available (issue #5); the
funder and signature type always stay in the plaintext TOML. On non-macOS, or
when the Keychain is unavailable, the key falls back to the TOML. Deliberately
outside any git working tree. The execution-live flag is never persisted -
every session starts in dry-run.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from polymarket_tui.core import keychain

CONFIG_DIR = Path.home() / ".config" / "polymarket-tui"
CRED_PATH = CONFIG_DIR / "credentials.toml"


def key_backend() -> str:
    """Where the private key is (or would be) stored: 'keychain' or 'file'."""
    return "keychain" if keychain.available() else "file"


def _write_toml(
    funder: str, signature_type: int, private_key: str = "", builder_code: str = ""
) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    lines = [
        "# polymarket-tui credentials - plaintext, keep permissions 0600.",
        "# execution mode (dry/live) is intentionally not stored here.",
    ]
    if private_key:
        lines.append("# private key stored here (Keychain unavailable).")
    else:
        lines.append("# private key stored in the macOS Keychain, not this file.")
    lines.append(f'funder = "{funder}"')
    if private_key:
        lines.append(f'private_key = "{private_key}"')
    lines.append(f"signature_type = {signature_type}")
    # builder_code is not a secret; it lives here to stay out of source.
    if builder_code:
        lines.append(f'builder_code = "{builder_code}"')
    body = "\n".join(lines) + "\n"
    # Create with restrictive permissions before writing any secret.
    fd = os.open(CRED_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(body)
    CRED_PATH.chmod(0o600)
    return CRED_PATH


def load_credentials() -> dict | None:
    """Return {funder, private_key, signature_type, builder_code} or None.

    Migrates a key still sitting in the TOML into the Keychain on first read.
    builder_code is the optional Builders-Program attribution code (not a
    secret); it defaults to "" when the file predates enrollment.
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
    builder_code = str(data.get("builder_code", ""))

    # Transparent migration: a key still in the TOML moves to the Keychain and
    # the TOML is rewritten without it (but keeps the builder code).
    if file_key and keychain.available() and keychain.set_key(file_key):
        _write_toml(funder, signature_type, builder_code=builder_code)
        file_key = ""

    private_key = file_key
    if not private_key and keychain.available():
        private_key = keychain.get_key() or ""

    return {
        "funder": funder,
        "private_key": private_key,
        "signature_type": signature_type,
        "builder_code": builder_code,
    }


def save_credentials(
    funder: str, private_key: str, signature_type: int, builder_code: str = ""
) -> Path:
    """Persist credentials. The key goes to the Keychain when available; the TOML
    keeps only funder + signature type (+ optional builder code) in that case."""
    in_keychain = bool(private_key) and keychain.available() and keychain.set_key(private_key)
    return _write_toml(
        funder,
        signature_type,
        private_key="" if in_keychain else private_key,
        builder_code=builder_code,
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
