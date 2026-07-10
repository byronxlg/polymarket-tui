"""polymarket.com deep links and open/copy helpers.

Redemption of a won position is an on-chain transaction this client
intentionally does not send; these helpers let the user jump straight to the
market's web page (where redemption happens) instead of dead-ending.
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser

BASE_URL = "https://polymarket.com"


def market_url(event_slug: str = "", slug: str = "") -> str:
    """Web page for a market. Prefer the event slug (canonical, 200); the market
    slug 307-redirects to it. Returns "" when neither is known."""
    if event_slug:
        return f"{BASE_URL}/event/{event_slug}"
    if slug:
        return f"{BASE_URL}/market/{slug}"
    return ""


def open_in_browser(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def copy_to_clipboard(text: str) -> bool:
    """macOS pbcopy; no-op (False) elsewhere so callers can still show the URL."""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    except Exception:
        return False


def open_and_copy(url: str) -> str:
    """Open `url` and copy it, returning the toast that says what happened.

    A headless box opens nothing and a non-mac copies nothing, so the message
    reports which of the two actually landed rather than claiming both."""
    opened = open_in_browser(url)
    copied = copy_to_clipboard(url)
    note = "Opened" if opened else "Copied" if copied else "URL"
    suffix = "  (copied)" if copied and opened else ""
    return f"{note} {url}{suffix}"
