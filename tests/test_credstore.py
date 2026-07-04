"""Credstore round-trip, Keychain backend, and migration (issue #5)."""

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
        "builder_code": "",
    }


def test_key_in_keychain_not_toml(tmp_credstore):
    tmp_credstore.save_credentials("0xFunder", "deadbeef" * 8, 1)
    text = tmp_credstore.CRED_PATH.read_text()
    assert "deadbeef" not in text  # key is in the Keychain, not the file
    assert "0xFunder" in text
    assert tmp_credstore._fake.store[keychain.ACCOUNT] == "deadbeef" * 8


def test_file_fallback_when_keychain_unavailable(tmp_credstore):
    tmp_credstore._fake.enabled = False
    tmp_credstore.save_credentials("0xFunder", "abc123", 2)
    text = tmp_credstore.CRED_PATH.read_text()
    assert 'private_key = "abc123"' in text  # falls back to the TOML
    assert tmp_credstore.load_credentials()["private_key"] == "abc123"


def test_migration_moves_key_out_of_toml(tmp_credstore):
    # Simulate a legacy TOML that still holds the key.
    tmp_credstore.CONFIG_DIR.mkdir(parents=True)
    tmp_credstore.CRED_PATH.write_text(
        'funder = "0xF"\nprivate_key = "legacykey"\nsignature_type = 1\n'
    )
    loaded = tmp_credstore.load_credentials()
    assert loaded["private_key"] == "legacykey"
    # After migration the file no longer holds the key; the Keychain does.
    assert "legacykey" not in tmp_credstore.CRED_PATH.read_text()
    assert tmp_credstore._fake.store[keychain.ACCOUNT] == "legacykey"


def test_load_missing_returns_none(tmp_credstore):
    assert tmp_credstore.load_credentials() is None


def test_clear_removes_file_and_keychain(tmp_credstore):
    tmp_credstore.save_credentials("0xF", "k", 2)
    assert tmp_credstore._fake.store  # key present
    assert tmp_credstore.clear_credentials() is True
    assert tmp_credstore.load_credentials() is None
    assert tmp_credstore._fake.store == {}
    assert tmp_credstore.clear_credentials() is False


def test_corrupt_file_returns_none(tmp_credstore):
    tmp_credstore.CONFIG_DIR.mkdir(parents=True)
    tmp_credstore.CRED_PATH.write_text("not [valid toml{{")
    assert tmp_credstore.load_credentials() is None


def test_builder_code_round_trip(tmp_credstore):
    code = "0x" + "ab" * 32
    tmp_credstore.save_credentials("0xF", "deadbeef" * 8, 1, builder_code=code)
    text = tmp_credstore.CRED_PATH.read_text()
    assert f'builder_code = "{code}"' in text  # not a secret, stays in the TOML
    assert tmp_credstore.load_credentials()["builder_code"] == code


def test_builder_code_omitted_when_empty(tmp_credstore):
    tmp_credstore.save_credentials("0xF", "k", 1)
    assert "builder_code" not in tmp_credstore.CRED_PATH.read_text()
    assert tmp_credstore.load_credentials()["builder_code"] == ""


def test_builder_code_survives_key_migration(tmp_credstore):
    # Legacy TOML with the key still inline AND a builder code present.
    code = "0x" + "cd" * 32
    tmp_credstore.CONFIG_DIR.mkdir(parents=True)
    tmp_credstore.CRED_PATH.write_text(
        f'funder = "0xF"\nprivate_key = "legacykey"\nsignature_type = 1\n'
        f'builder_code = "{code}"\n'
    )
    loaded = tmp_credstore.load_credentials()
    assert loaded["private_key"] == "legacykey"
    assert loaded["builder_code"] == code
    # Rewrite dropped the key but kept the builder code.
    text = tmp_credstore.CRED_PATH.read_text()
    assert "legacykey" not in text
    assert code in text
