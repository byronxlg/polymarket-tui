"""macOS Keychain backend for the Polymarket private key (issue #5).

Uses the `security` CLI so there is no extra dependency. Only the private key
lives here; funder and signature type stay in the plaintext TOML. On non-macOS
(or when `security` is missing) every function reports unavailable and callers
fall back to the TOML.

The key is passed to `security` on the command line, so it is briefly visible
to `ps`; the win is that no plaintext copy remains on disk between runs. `-A`
grants access without an interactive prompt on each run (the tool is launched as
a fresh process each time), trading a keychain ACL prompt for usable CLI UX.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

SERVICE = "polymarket-tui"
ACCOUNT = "private_key"


def available() -> bool:
    return sys.platform == "darwin" and shutil.which("security") is not None


def get_key() -> str | None:
    if not available():
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    key = out.stdout.strip()
    return key or None


def set_key(key: str) -> bool:
    if not available() or not key:
        return False
    try:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s", SERVICE,
                "-a", ACCOUNT,
                "-w", key,
                "-U",  # update if the item already exists
                "-A",  # allow access without a per-run prompt
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def delete_key() -> bool:
    """Remove the key. True if an entry existed and was deleted."""
    if not available():
        return False
    try:
        subprocess.run(
            ["security", "delete-generic-password", "-s", SERVICE, "-a", ACCOUNT],
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
