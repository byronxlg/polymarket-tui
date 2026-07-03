"""Watchlist persistence: a JSON list of event slugs."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "polymarket-tui"


class Watchlist:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DATA_DIR / "watchlist.json"
        self._slugs: list[str] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
            if isinstance(data, list):
                self._slugs = [s for s in data if isinstance(s, str)]
        except (OSError, json.JSONDecodeError):
            self._slugs = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._slugs, indent=2))

    @property
    def slugs(self) -> list[str]:
        return list(self._slugs)

    def __contains__(self, slug: str) -> bool:
        return slug in self._slugs

    def toggle(self, slug: str) -> bool:
        """Toggle membership; returns True if the slug is now watched."""
        if slug in self._slugs:
            self._slugs.remove(slug)
            self._save()
            return False
        self._slugs.append(slug)
        self._save()
        return True
