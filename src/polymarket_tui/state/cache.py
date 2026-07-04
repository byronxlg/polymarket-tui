"""Startup cache: the last home event list, rendered instantly on boot.

Stale-while-revalidate for perceived load time (issue #45): the home screen
shows the previous session's list the moment it paints, then the live fetch
replaces it. Prices in the cached render can be hours old, so callers should
say so until fresh data lands.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from polymarket_tui.models.market import Event

CACHE_DIR = Path.home() / ".local" / "share" / "polymarket-tui" / "cache"
MAX_AGE_S = 24 * 3600


def _path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return CACHE_DIR / f"{safe}.json"


def save_events(key: str, events: list[Event]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "at": time.time(),
            "events": [e.model_dump(mode="json", by_alias=True) for e in events],
        }
        _path(key).write_text(json.dumps(payload))
    except Exception:
        pass  # cache is best-effort; never let it break a live render


def load_events(key: str, max_age_s: float = MAX_AGE_S) -> list[Event] | None:
    try:
        payload = json.loads(_path(key).read_text())
        if time.time() - float(payload.get("at", 0)) > max_age_s:
            return None
        events = [Event.model_validate(e) for e in payload["events"]]
        return events or None
    except Exception:
        return None
