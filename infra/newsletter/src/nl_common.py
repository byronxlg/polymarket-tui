"""Shared helpers for the newsletter lambdas (stdlib only)."""

import re
import secrets

# Deliberately loose: the confirmation email is the real validation. This only
# rejects obvious garbage so we don't burn SES sends on it.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LEN = 254


def normalize_email(raw: object) -> str | None:
    """Lowercased, trimmed address, or None if it can't be an email."""
    if not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if not email or len(email) > MAX_EMAIL_LEN or not EMAIL_RE.match(email):
        return None
    return email


def new_token() -> str:
    """Unguessable per-subscriber secret for confirm/unsubscribe links."""
    return secrets.token_urlsafe(32)
