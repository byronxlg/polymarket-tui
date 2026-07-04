"""Offline key/funder pairing proof (issue #6).

Vectors are from Polymarket SDK/rs-clob-client tests and were reproduced against
a real type-1 account before shipping.
"""

from polymarket_tui.core.proxy import check_pairing, expected_funder, poly_proxy_address

# Anvil default EOA -> its Polymarket type-1 proxy (SDK test vector).
ANVIL_EOA = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
ANVIL_PROXY = "0x365f0cA36ae1F641E02Fe3b7743673DA42A13a70"
# Real on-chain type-1 pair.
REAL_EOA = "0x339a9731D4c1ea6861db006ad592b83E49C9398e"
REAL_PROXY = "0xba734a6a711c9f13b8f7366572a4f9817a0dac46"


def test_poly_proxy_address_matches_known_vectors():
    assert poly_proxy_address(ANVIL_EOA).lower() == ANVIL_PROXY.lower()
    assert poly_proxy_address(REAL_EOA).lower() == REAL_PROXY.lower()


def test_type1_proven_when_funder_matches_derived():
    state, _ = check_pairing(ANVIL_EOA, ANVIL_PROXY, 1)
    assert state == "proven"


def test_type1_mismatch_when_funder_wrong():
    state, detail = check_pairing(ANVIL_EOA, REAL_PROXY, 1)
    assert state == "mismatch"
    assert ANVIL_PROXY.lower() in detail.lower()


def test_type0_exact_match():
    assert check_pairing(ANVIL_EOA, ANVIL_EOA, 0)[0] == "proven"
    assert check_pairing(ANVIL_EOA, REAL_EOA, 0)[0] == "mismatch"


def test_type2_is_unproven_never_mismatch():
    # Safe derivation is not reliably reproducible; must not false-alarm.
    state, _ = check_pairing(ANVIL_EOA, REAL_PROXY, 2)
    assert state == "unproven"
    assert expected_funder(ANVIL_EOA, 2) is None


def test_missing_data_is_unproven():
    assert check_pairing("", ANVIL_PROXY, 1)[0] == "unproven"
    assert check_pairing(ANVIL_EOA, "", 1)[0] == "unproven"
