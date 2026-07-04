"""Prove a private key controls a funder before order time (issue #6).

A Polymarket funder is not the signer EOA. For proxy accounts the funder is a
contract deployed deterministically (CREATE2) from the owner EOA, so we can
derive the expected funder from the key offline - no RPC, no order needed - and
compare it to the configured funder.

Signature types:
- 0 (EOA):   the signer IS the funder. Exact-match check.
- 1 (PROXY): Polymarket proxy wallet (email/magic accounts). Derivation below is
             verified against real accounts and the SDK test vectors.
- 2 (SAFE):  Gnosis-Safe accounts. The public derivation could not be reproduced
             reliably, so we do NOT assert a mismatch for it - reporting a false
             mismatch on a correct key would be worse than staying honest.

CREATE2: address = last20( keccak256( 0xff ++ factory ++ salt ++ initCodeHash ) )
"""

from __future__ import annotations

from eth_utils import keccak, to_checksum_address

# Polygon (chainId 137) Polymarket proxy-wallet factory (signature type 1).
_POLY_PROXY_FACTORY = "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"
_POLY_PROXY_INIT_CODE_HASH = bytes.fromhex(
    "d21df8dc65880a8606f09fe0ce3df9b8869287ab0b058be05aa9e8af6330a00b"
)


def _create2(factory: str, salt: bytes, init_code_hash: bytes) -> str:
    body = b"\xff" + bytes.fromhex(factory[2:]) + salt + init_code_hash
    return to_checksum_address(keccak(body)[12:])


def poly_proxy_address(signer: str) -> str:
    """Funder proxy for a Polymarket type-1 (email/magic) account.

    salt = keccak256(encodePacked(address)) = keccak256 of the raw 20 owner bytes.
    Verified: signer 0x25D9..1973 -> 0x2011..845B; anvil EOA -> 0x365f..3a70.
    """
    salt = keccak(bytes.fromhex(signer[2:]))
    return _create2(_POLY_PROXY_FACTORY, salt, _POLY_PROXY_INIT_CODE_HASH)


def expected_funder(signer: str, signature_type: int) -> str | None:
    """The funder address this signer should control, or None when it cannot be
    derived offline (type 2, or an unknown type)."""
    if not signer:
        return None
    try:
        if signature_type == 0:
            return to_checksum_address(signer)
        if signature_type == 1:
            return poly_proxy_address(signer)
    except Exception:
        return None
    return None  # type 2 (Safe) and anything else: not derivable here


def check_pairing(signer: str, funder: str, signature_type: int) -> tuple[str, str]:
    """Verdict on whether `signer` controls `funder`.

    Returns (state, message) where state is one of:
    - "proven":   the key authoritatively controls the funder
    - "mismatch": the key does NOT control the funder (wrong key/funder)
    - "unproven": cannot be checked offline (type 2 or missing data)
    """
    if not signer or not funder:
        return "unproven", "signer or funder missing"
    derived = expected_funder(signer, signature_type)
    if derived is None:
        if signature_type == 2:
            return (
                "unproven",
                "type 2 (Safe): key/funder pairing is only proven when an order posts",
            )
        return "unproven", f"signature type {signature_type} cannot be checked offline"
    if derived.lower() == funder.lower():
        return "proven", "key controls this funder (derived on-chain address matches)"
    return (
        "mismatch",
        f"this key controls funder {derived}, not {to_checksum_address(funder)}",
    )
