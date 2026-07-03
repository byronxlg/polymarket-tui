"""Credstore round-trip and settings fallback."""

from __future__ import annotations

import stat

import pytest

from polymarket_tui.core import credstore


@pytest.fixture
def tmp_credstore(tmp_path, monkeypatch):
    monkeypatch.setattr(credstore, "CONFIG_DIR", tmp_path / "polymarket-tui")
    monkeypatch.setattr(credstore, "CRED_PATH", tmp_path / "polymarket-tui" / "credentials.toml")
    return credstore


def test_round_trip(tmp_credstore):
    path = tmp_credstore.save_credentials("0xFunder", "deadbeef" * 8, 1)
    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    loaded = tmp_credstore.load_credentials()
    assert loaded == {
        "funder": "0xFunder",
        "private_key": "deadbeef" * 8,
        "signature_type": 1,
    }


def test_load_missing_returns_none(tmp_credstore):
    assert tmp_credstore.load_credentials() is None


def test_clear(tmp_credstore):
    tmp_credstore.save_credentials("0xF", "k", 2)
    assert tmp_credstore.clear_credentials() is True
    assert tmp_credstore.load_credentials() is None
    assert tmp_credstore.clear_credentials() is False


def test_corrupt_file_returns_none(tmp_credstore):
    tmp_credstore.CONFIG_DIR.mkdir(parents=True)
    tmp_credstore.CRED_PATH.write_text("not [valid toml{{")
    assert tmp_credstore.load_credentials() is None
