"""Watchlist persistence: starred event slugs and followed users."""

from __future__ import annotations

import json
from pathlib import Path

from polymarket_tui.core.fileio import write_atomic

DATA_DIR = Path.home() / ".local" / "share" / "polymarket-tui"


class Watchlist:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DATA_DIR / "watchlist.json"
        self._slugs: list[str] = []
        self._users: list[dict[str, str]] = []  # {"address": ..., "name": ...}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, list):  # v1 format: bare list of event slugs
            self._slugs = [s for s in data if isinstance(s, str)]
        elif isinstance(data, dict):
            self._slugs = [s for s in data.get("events", []) if isinstance(s, str)]
            self._users = [
                u
                for u in data.get("users", [])
                if isinstance(u, dict) and isinstance(u.get("address"), str)
            ]

    def _save(self) -> None:
        # Atomic: a crash mid-write must not truncate the file - _load treats
        # corrupt JSON as empty and the next toggle would persist the wipe.
        payload = {"events": self._slugs, "users": self._users}
        write_atomic(self._path, json.dumps(payload, indent=2))

    # -- events ---------------------------------------------------------------

    @property
    def slugs(self) -> list[str]:
        return list(self._slugs)

    def __contains__(self, slug: str) -> bool:
        return slug in self._slugs

    def toggle(self, slug: str) -> bool:
        """Toggle membership; returns True if the slug is now watched."""
        if slug in self._slugs:
            self._slugs.remove(slug)
        else:
            self._slugs.append(slug)
        self._save()
        return slug in self._slugs

    # -- users ------------------------------------------------------------------

    @property
    def users(self) -> list[dict[str, str]]:
        return list(self._users)

    def is_watched_user(self, address: str) -> bool:
        return any(u["address"].lower() == address.lower() for u in self._users)

    def toggle_user(self, address: str, name: str) -> bool:
        """Toggle a followed user; returns True if now watched."""
        if self.is_watched_user(address):
            self._users = [u for u in self._users if u["address"].lower() != address.lower()]
        else:
            self._users.append({"address": address, "name": name})
        self._save()
        return self.is_watched_user(address)
