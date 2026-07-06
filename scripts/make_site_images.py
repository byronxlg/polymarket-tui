"""Regenerate the landing page's derived images.

Produces:
  site/assets/og.png           1200x630 social preview (og:image / twitter card)
  site/assets/demo-poster.png  readable crop of the demo's poster frame, shown
                               instead of the player on small screens

Run after re-recording site/assets/demo.cast or changing the hero:

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

# demo-poster.png geometry: widen the page rail so the 160-col terminal
# renders large, then crop the top-left ~55 columns - phone-width readable.
WIDE_RAIL_PX = 2400
POSTER_W, POSTER_H = 790, 610


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
        page.wait_for_timeout(2500)  # let the player draw a frame
        page.screenshot(path=str(ASSETS / "og.png"))
        page.close()

        # -- demo-poster.png: recreate the player paused on its poster frame
        # inside an artificially wide rail, then crop the top-left corner --
        page = browser.new_page(viewport={"width": WIDE_RAIL_PX + 160, "height": 1400})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.add_style_tag(content=f".rail {{ width: {WIDE_RAIL_PX}px; max-width: none; }}")
        page.evaluate(
            """() => {
              const holder = document.getElementById("demo-player");
              holder.hidden = false;
              holder.innerHTML = "";
              AsciinemaPlayer.create("assets/demo.cast", holder, {
                autoPlay: false, controls: false, fit: "width",
                theme: "asciinema", poster: "npt:0:2",
              });
            }"""
        )
        page.wait_for_selector(".ap-terminal")
        page.wait_for_timeout(1500)  # font load + poster paint
        box = page.locator(".ap-terminal").bounding_box()
        assert box and box["width"] > 2000, f"terminal did not widen: {box}"
        page.screenshot(
            path=str(ASSETS / "demo-poster.png"),
            clip={"x": box["x"], "y": box["y"], "width": POSTER_W, "height": POSTER_H},
        )
        page.close()
        browser.close()

    for name in ("og.png", "demo-poster.png"):
        print(name, (ASSETS / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
