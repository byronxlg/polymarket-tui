"""CLOB auth bootstrap.

V2's /auth/api-key endpoint is Cloudflare-blocked, so L2 creds are derived via the
legacy V1 client and handed to the V2 client (creds are deterministic from the
wallet signature, so they are interchangeable). Runs in a thread - both clients
are synchronous.
"""

from __future__ import annotations

import asyncio
import logging

from polymarket_tui.core.config import Settings

log = logging.getLogger(__name__)

POLYGON_CHAIN_ID = 137


class AuthError(Exception):
    pass


def _bootstrap_sync(settings: Settings):
    from py_clob_client.client import ClobClient as V1Client
    from py_clob_client_v2 import ApiCreds, ClobClient

    v1 = V1Client(
        host=settings.polymarket_host,
        key=settings.polymarket_private_key,
        chain_id=POLYGON_CHAIN_ID,
        signature_type=settings.polymarket_signature_type,
        funder=settings.polymarket_funder,
    )
    v1_creds = v1.create_or_derive_api_creds()

    client = ClobClient(
        host=settings.polymarket_host,
        chain_id=POLYGON_CHAIN_ID,
        key=settings.polymarket_private_key,
        creds=ApiCreds(
            api_key=v1_creds.api_key,
            api_secret=v1_creds.api_secret,
            api_passphrase=v1_creds.api_passphrase,
        ),
        signature_type=settings.polymarket_signature_type,
        funder=settings.polymarket_funder,
    )
    return client


def _l2_creds_sync(settings: Settings) -> dict:
    from py_clob_client.client import ClobClient as V1Client

    v1 = V1Client(
        host=settings.polymarket_host,
        key=settings.polymarket_private_key,
        chain_id=POLYGON_CHAIN_ID,
        signature_type=settings.polymarket_signature_type,
        funder=settings.polymarket_funder,
    )
    creds = v1.create_or_derive_api_creds()
    return {
        "apiKey": creds.api_key,
        "secret": creds.api_secret,
        "passphrase": creds.api_passphrase,
    }


async def derive_l2_creds(settings: Settings) -> dict | None:
    """L2 creds (apiKey/secret/passphrase) for the authenticated /ws/user socket.
    Deterministic from the wallet signature. None if auth is not configured."""
    if not settings.can_auth:
        return None
    try:
        return await asyncio.to_thread(_l2_creds_sync, settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("L2 cred derivation failed: %s", exc)
        return None


async def bootstrap_authed_client(settings: Settings):
    """Return an authenticated py-clob-client-v2 ClobClient, or raise AuthError."""
    if not settings.can_auth:
        raise AuthError("missing POLYMARKET_PRIVATE_KEY / POLYMARKET_FUNDER")
    try:
        return await asyncio.to_thread(_bootstrap_sync, settings)
    except Exception as exc:  # noqa: BLE001 - surface every bootstrap failure as AuthError
        log.warning("CLOB auth bootstrap failed: %s", exc)
        raise AuthError(str(exc)) from exc
