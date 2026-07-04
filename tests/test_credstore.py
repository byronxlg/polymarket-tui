"""Credstore round-trip and the legacy Keychain -> file migration."""

from __future__ import annotations

import stat

import pytest

from polymarket_tui.core import credstore, keychain


class FakeKeychain:
    """In-memory stand-in so tests never touch the real login Keychain."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.store: dict[str, str] = {}

    def available(self) -> bool:
        return self.enabled

    def get_key(self) -> str | None:
        return self.store.get(keychain.ACCOUNT) if self.enabled else None

    def set_key(self, key: str) -> bool:
        if not self.enabled or not key:
            return False
        self.store[keychain.ACCOUNT] = key
        return True

    def delete_key(self) -> bool:
        if not self.enabled:
            return False
        return self.store.pop(keychain.ACCOUNT, None) is not None


@pytest.fixture
def fake_keychain(monkeypatch):
    fake = FakeKeychain(enabled=True)
    for name in ("available", "get_key", "set_key", "delete_key"):
        monkeypatch.setattr(keychain, name, getattr(fake, name))
    return fake


@pytest.fixture
def tmp_credstore(tmp_path, monkeypatch, fake_keychain):
    monkeypatch.setattr(credstore, "CONFIG_DIR", tmp_path / "polymarket-tui")
    monkeypatch.setattr(credstore, "CRED_PATH", tmp_path / "polymarket-tui" / "credentials.toml")
    credstore._fake = fake_keychain  # exposed for assertions
    return credstore


def test_round_trip(tmp_credstore):
    path = tmp_credstore.save_credentials("0xFunder", "deadbeef" * 8, 1)
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    loaded = tmp_credstore.load_credentials()
    assert loaded == {
        "funder": "0xFunder",
        "private_key": "deadbeef" * 8,
        "signature_type": 1,
        "execution_live": False,
    }


def test_execution_live_round_trip(tmp_credstore):
    tmp_credstore.save_credentials("0xFunder", "deadbeef" * 8, 1, execution_live=True)
    assert tmp_credstore.load_credentials()["execution_live"] is True
    # save_execution_live flips just the flag, keeping the credentials.
    tmp_credstore.save_execution_live(False)
    loaded = tmp_credstore.load_credentials()
    assert loaded["execution_live"] is False
    assert loaded["funder"] == "0xFunder"
    assert loaded["private_key"] == "deadbeef" * 8


def test_key_stays_in_file_not_keychain(tmp_credstore):
    """Keychain retired: saving never writes the Keychain, key lives in the TOML."""
    tmp_credstore.save_credentials("0xFunder", "deadbeef" * 8, 1)
    text = tmp_credstore.CRED_PATH.read_text()
    assert 'private_key = "' + "deadbeef" * 8 + '"' in text
    assert keychain.ACCOUNT not in tmp_credstore._fake.store


def test_legacy_keychain_key_migrates_into_file(tmp_credstore):
    """A key left in the Keychain by an older build moves into the TOML once."""
    tmp_credstore._fake.store[keychain.ACCOUNT] = "cafe" * 16
    tmp_credstore._write_toml("0xFunder", 1)  # legacy file without a key
    loaded = tmp_credstore.load_credentials()
    assert loaded["private_key"] == "cafe" * 16
    assert keychain.ACCOUNT not in tmp_credstore._fake.store  # entry deleted
    assert 'private_key = "' + "cafe" * 16 + '"' in tmp_credstore.CRED_PATH.read_text()


def test_key_in_toml_stays_in_toml(tmp_credstore):
    # A TOML that holds the key is the steady state - no Keychain writes.
    tmp_credstore.CONFIG_DIR.mkdir(parents=True)
    tmp_credstore.CRED_PATH.write_text(
        'funder = "0xF"\nprivate_key = "filekey"\nsignature_type = 1\n'
    )
    loaded = tmp_credstore.load_credentials()
    assert loaded["private_key"] == "filekey"
    assert "filekey" in tmp_credstore.CRED_PATH.read_text()
    assert keychain.ACCOUNT not in tmp_credstore._fake.store


def test_load_missing_returns_none(tmp_credstore):
    assert tmp_credstore.load_credentials() is None


def test_clear_removes_file_and_keychain(tmp_credstore):
    tmp_credstore.save_credentials("0xF", "k", 2)
    # A stale legacy Keychain entry is cleared too.
    tmp_credstore._fake.store[keychain.ACCOUNT] = "stale"
    assert tmp_credstore.clear_credentials() is True
    assert tmp_credstore.load_credentials() is None
    assert tmp_credstore._fake.store == {}
    assert tmp_credstore.clear_credentials() is False


def test_corrupt_file_returns_none(tmp_credstore):
    tmp_credstore.CONFIG_DIR.mkdir(parents=True)
    tmp_credstore.CRED_PATH.write_text("not [valid toml{{")
    assert tmp_credstore.load_credentials() is None
