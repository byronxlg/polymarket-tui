"""UI preferences persistence: display density (condensed/spacious)."""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "polymarket-tui"

DENSITIES = ("condensed", "spacious")
DEFAULT_DENSITY = "condensed"


def _prefs_path(path: Path | None) -> Path:
    return path or DATA_DIR / "ui.json"


def load_density(path: Path | None = None) -> str:
    """PMTUI_DENSITY env wins; otherwise the saved pref; default condensed."""
    env = os.environ.get("PMTUI_DENSITY", "").strip().lower()
    if env in DENSITIES:
        return env
    try:
        data = json.loads(_prefs_path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return DEFAULT_DENSITY
    density = data.get("density") if isinstance(data, dict) else None
    return density if density in DENSITIES else DEFAULT_DENSITY


def save_density(density: str, path: Path | None = None) -> None:
    p = _prefs_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data["density"] = density
    p.write_text(json.dumps(data, indent=2))
