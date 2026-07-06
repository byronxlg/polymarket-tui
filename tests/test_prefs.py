"""UI prefs: density load/save round-trip, env override, bad-file tolerance."""

from __future__ import annotations

import json

from polymarket_tui.state.prefs import (
    load_density,
    load_theme,
    save_density,
    save_theme,
)


def test_default_when_missing(tmp_path):
    assert load_density(tmp_path / "ui.json") == "condensed"


def test_round_trip(tmp_path):
    path = tmp_path / "ui.json"
    save_density("spacious", path)
    assert load_density(path) == "spacious"
    save_density("condensed", path)
    assert load_density(path) == "condensed"


def test_env_override_wins(tmp_path, monkeypatch):
    path = tmp_path / "ui.json"
    save_density("condensed", path)
    monkeypatch.setenv("PMTUI_DENSITY", "spacious")
    assert load_density(path) == "spacious"


def test_env_invalid_value_ignored(tmp_path, monkeypatch):
    path = tmp_path / "ui.json"
    save_density("spacious", path)
    monkeypatch.setenv("PMTUI_DENSITY", "cozy")
    assert load_density(path) == "spacious"


def test_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text("{not json")
    assert load_density(path) == "condensed"


def test_unknown_saved_value_falls_back(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text(json.dumps({"density": "cozy"}))
    assert load_density(path) == "condensed"


def test_save_preserves_other_keys(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text(json.dumps({"future_pref": 1}))
    save_density("spacious", path)
    data = json.loads(path.read_text())
    assert data == {"future_pref": 1, "density": "spacious"}


def test_theme_default_when_missing(tmp_path):
    assert load_theme(tmp_path / "ui.json") == "pmtui"


def test_theme_round_trip(tmp_path):
    path = tmp_path / "ui.json"
    save_theme("gruvbox", path)
    assert load_theme(path) == "gruvbox"
    save_theme("pmtui", path)
    assert load_theme(path) == "pmtui"


def test_theme_env_override_wins(tmp_path, monkeypatch):
    path = tmp_path / "ui.json"
    save_theme("gruvbox", path)
    monkeypatch.setenv("PMTUI_THEME", "nord")
    assert load_theme(path) == "nord"


def test_theme_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text("{not json")
    assert load_theme(path) == "pmtui"


def test_theme_and_density_coexist(tmp_path):
    path = tmp_path / "ui.json"
    save_density("spacious", path)
    save_theme("dracula", path)
    assert load_density(path) == "spacious"
    assert load_theme(path) == "dracula"
    data = json.loads(path.read_text())
    assert data == {"density": "spacious", "theme": "dracula"}
