"""Regenerate the landing page's derived image.

Produces:
  site/assets/og.png           1200x630 social preview (og:image / twitter card)

Run after changing the hero (the card is a screenshot of it):

    uv run --with playwright python scripts/make_site_images.py

(one-time: uv run --with playwright playwright install chromium)
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parent.parent / "site"
ASSETS = SITE / "assets"


def serve_site() -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def main() -> None:
    port = serve_site()
    url = f"http://127.0.0.1:{port}/index.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # -- og.png: the hero at standard social-card size --
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        # Let the launch video play past its opening title so the visible
        # strip under the hero text shows the TUI, not a black frame.
        page.wait_for_timeout(11000)
        page.screenshot(path=str(ASSETS / "og.png"))
        page.close()
        browser.close()

    print("og.png", (ASSETS / "og.png").stat().st_size, "bytes")


if __name__ == "__main__":
    main()
