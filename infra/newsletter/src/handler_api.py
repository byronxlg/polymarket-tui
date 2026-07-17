"""Signup API: POST /subscribe, GET /confirm, GET|POST /unsubscribe.

Behind API Gateway (payload v2). Double opt-in: subscribing stores a pending
row and emails a confirm link; only confirmed rows receive digests. /subscribe
answers the same generic 200 whether or not the address was new, so it cannot
be used to probe who is subscribed.
"""

import base64
import hmac
import json
import logging
import os
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import boto3
from digest_render import (
    SITE_NAME,
    page_html,
    render_confirm_html,
    render_confirm_text,
)
from nl_common import new_token, normalize_email

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
API_BASE_URL = os.environ["API_BASE_URL"]
SITE_URL = os.environ["SITE_URL"]

RESEND_COOLDOWN_S = 15 * 60

_table = boto3.resource("dynamodb").Table(TABLE_NAME)
_ses = boto3.client("sesv2")


def _json(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _page(status: int, title: str, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "text/html; charset=utf-8"},
        "body": page_html(title, message, SITE_URL),
    }


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _send_confirmation(email: str, token: str) -> None:
    confirm_url = f"{API_BASE_URL}/confirm?{urlencode({'email': email, 'token': token})}"
    _ses.send_email(
        FromEmailAddress=f"{SITE_NAME} <{SENDER_EMAIL}>",
        Destination={"ToAddresses": [email]},
        Content={
            "Simple": {
                "Subject": {"Data": f"Confirm your {SITE_NAME} daily digest"},
                "Body": {
                    "Text": {"Data": render_confirm_text(confirm_url)},
                    "Html": {"Data": render_confirm_html(confirm_url)},
                },
            }
        },
    )


def _subscribe(event: dict) -> dict:
    body_raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8", errors="replace")
    try:
        body = json.loads(body_raw)
    except ValueError:
        return _json(400, {"ok": False, "error": "invalid_body"})
    if not isinstance(body, dict):
        return _json(400, {"ok": False, "error": "invalid_body"})

    # Honeypot: the site form has a hidden "website" field humans never fill.
    generic_ok = _json(200, {"ok": True})
    if body.get("website"):
        return generic_ok

    email = normalize_email(body.get("email"))
    if email is None:
        return _json(400, {"ok": False, "error": "invalid_email"})

    item = (_table.get_item(Key={"email": email}).get("Item")) or {}
    if item.get("status") == "confirmed":
        return generic_ok
    if int(item.get("last_sent_at") or 0) > time.time() - RESEND_COOLDOWN_S:
        return generic_ok

    token = str(item.get("token") or new_token())
    _table.put_item(
        Item={
            "email": email,
            "token": token,
            "status": "pending",
            "created_at": str(item.get("created_at") or _now_iso()),
            "last_sent_at": int(time.time()),
        }
    )
    try:
        _send_confirmation(email, token)
    except Exception:
        # SES sandbox rejects unverified recipients; never leak that outward.
        logger.exception("confirmation send failed for %s", email)
    return generic_ok


def _lookup(event: dict) -> tuple[str, dict] | None:
    """Return (email, item) when the email+token in the query string match."""
    params = event.get("queryStringParameters") or {}
    email = normalize_email(params.get("email"))
    token = params.get("token") or ""
    if email is None or not token:
        return None
    item = (_table.get_item(Key={"email": email}).get("Item")) or {}
    if not item or not hmac.compare_digest(str(item.get("token") or ""), token):
        return None
    return email, item


def _confirm(event: dict) -> dict:
    match = _lookup(event)
    if match is None:
        return _page(
            400,
            "Link not valid",
            "This confirmation link is not valid. Sign up again on the site to get a fresh one.",
        )
    email, item = match
    if item.get("status") != "confirmed":
        _table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :c, confirmed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": "confirmed", ":t": _now_iso()},
        )
    return _page(
        200,
        "Subscribed",
        "You're on the list. The daily digest arrives each morning; "
        "every email has an unsubscribe link.",
    )


def _unsubscribe(event: dict, method: str) -> dict:
    match = _lookup(event)
    if match is None:
        if method == "POST":
            return _json(400, {"ok": False})
        return _page(
            400,
            "Link not valid",
            "This unsubscribe link is not valid. Reply to any digest email "
            "if you keep receiving it.",
        )
    email, _item = match
    _table.update_item(
        Key={"email": email},
        UpdateExpression="SET #s = :u, unsubscribed_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":u": "unsubscribed", ":t": _now_iso()},
    )
    if method == "POST":  # RFC 8058 one-click
        return _json(200, {"ok": True})
    return _page(200, "Unsubscribed", "Done. No more digests will be sent to this address.")


def lambda_handler(event: dict, _context: object) -> dict:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "")
    path = event.get("rawPath", "")

    if method == "POST" and path == "/subscribe":
        return _subscribe(event)
    if method == "GET" and path == "/confirm":
        return _confirm(event)
    if path == "/unsubscribe" and method in ("GET", "POST"):
        return _unsubscribe(event, method)
    return _json(404, {"ok": False, "error": "not_found"})
