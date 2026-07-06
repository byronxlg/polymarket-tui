"""UI preferences persistence: display density and the picked theme."""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "polymarket-tui"

DENSITIES = ("condensed", "spacious")
DEFAULT_DENSITY = "condensed"

DEFAULT_THEME = "pmtui"


def _prefs_path(path: Path | None) -> Path:
    return path or DATA_DIR / "ui.json"


def _save_pref(key: str, value: str, path: Path | None) -> None:
    """Merge one key into ui.json, tolerating a missing or corrupt file."""
    p = _prefs_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[key] = value
    p.write_text(json.dumps(data, indent=2))


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
    _save_pref("density", density, path)


def load_theme(path: Path | None = None) -> str:
    """PMTUI_THEME env wins; otherwise the saved pref; default pmtui.

    The name is not validated here - the set of themes varies by Textual
    version, so the app checks it against its registered themes and falls
    back to pmtui if the saved name is unknown.
    """
    env = os.environ.get("PMTUI_THEME", "").strip()
    if env:
        return env
    try:
        data = json.loads(_prefs_path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return DEFAULT_THEME
    theme = data.get("theme") if isinstance(data, dict) else None
    return theme if isinstance(theme, str) and theme else DEFAULT_THEME


def save_theme(theme: str, path: Path | None = None) -> None:
    _save_pref("theme", theme, path)
