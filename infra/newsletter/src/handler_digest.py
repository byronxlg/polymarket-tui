"""Daily digest sender, invoked by EventBridge Scheduler.

Builds the digest once, then sends one personalized email per confirmed
subscriber (the unsubscribe link differs per recipient). Per-recipient
failures are logged and skipped; the run is never retried automatically -
a retry after a partial send would double-deliver.
"""

import logging
import os
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

import boto3
from blurb import generate_headlines
from boto3.dynamodb.conditions import Attr
from digest_data import build_digest, digest_is_empty
from digest_render import (
    SITE_NAME,
    UNSUB_PLACEHOLDER,
    render_html,
    render_subject,
    render_text,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
API_BASE_URL = os.environ["API_BASE_URL"]
SITE_URL = os.environ["SITE_URL"]
BLURB_MODEL_ID = os.environ.get("BLURB_MODEL_ID", "")  # empty disables the blurb

SEND_GAP_S = 0.15  # stay far under SES rate limits without dragging the run out

_table = boto3.resource("dynamodb").Table(TABLE_NAME)
_ses = boto3.client("sesv2")


def _confirmed_subscribers() -> list[dict]:
    items: list[dict] = []
    kwargs = {"FilterExpression": Attr("status").eq("confirmed")}
    while True:
        page = _table.scan(**kwargs)
        items.extend(page.get("Items", []))
        last = page.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def _build_mime(subject: str, text: str, html_body: str, email: str, unsub_url: str) -> bytes:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{SITE_NAME} <{SENDER_EMAIL}>"
    msg["To"] = email
    msg["List-Unsubscribe"] = f"<{unsub_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg.as_bytes()


def lambda_handler(_event: dict, _context: object) -> dict:
    subscribers = _confirmed_subscribers()
    if not subscribers:
        logger.info("no confirmed subscribers; skipping digest build")
        return {"sent": 0, "failed": 0, "subscribers": 0}

    digest = build_digest()
    if digest_is_empty(digest):
        logger.error("every digest section came back empty; not sending")
        return {"sent": 0, "failed": 0, "subscribers": len(subscribers), "aborted": True}

    headlines = generate_headlines(digest, BLURB_MODEL_ID) if BLURB_MODEL_ID else {}
    digest["blurb"] = headlines.get("blurb")
    digest["preheader"] = headlines.get("preheader")

    subject = render_subject(digest["generated_at"], headlines.get("subject"))
    text_tpl = render_text(digest)
    html_tpl = render_html(digest, SITE_URL)

    sent = failed = 0
    for sub in subscribers:
        email = str(sub["email"])
        unsub_qs = urlencode({"email": email, "token": str(sub.get("token") or "")})
        unsub_url = f"{API_BASE_URL}/unsubscribe?{unsub_qs}"
        text = text_tpl.replace(UNSUB_PLACEHOLDER, unsub_url)
        html_body = html_tpl.replace(UNSUB_PLACEHOLDER, unsub_url)
        try:
            _ses.send_email(
                FromEmailAddress=f"{SITE_NAME} <{SENDER_EMAIL}>",
                Destination={"ToAddresses": [email]},
                Content={"Raw": {"Data": _build_mime(subject, text, html_body, email, unsub_url)}},
            )
            sent += 1
        except Exception:
            # Sandbox-mode SES rejects unverified recipients; keep going.
            logger.exception("digest send failed for %s", email)
            failed += 1
        time.sleep(SEND_GAP_S)

    summary = {"sent": sent, "failed": failed, "subscribers": len(subscribers)}
    logger.info("digest run complete: %s", summary)
    return summary
