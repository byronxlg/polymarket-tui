"""Regenerate the launch video's terminal stills from the recorded demo.

Produces the three product frames the Hyperframes composition holds on:

  brag/composition/assets/ui/book.png     the streaming order book
  brag/composition/assets/ui/order.png    the order ticket under the book
  brag/composition/assets/ui/dryrun.png   the DRY RUN toast

Each is the asciinema player paused on a frame of site/assets/demo.cast and
screenshotted at the terminal's own size, so the video always shows the UI the
demo recorded - no hand-built mockups, no frames of an older release.

The page itself no longer loads the player (site/README.md: one recording in
the hero, the launch video), so this script serves site/ and injects the
vendored player (assets/asciinema-player.*) into its own holder on the page;
the page's fonts and theme still apply.

Run after re-recording the demo, before rendering the video:

    uv run --with playwright python scripts/make_brag_stills.py

Times are seconds into the cast. Re-tune them when the tour in
scripts/record_demo.sh changes; the marker each one aims at is in the comment.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
UI = ROOT / "brag" / "composition" / "assets" / "ui"
RAIL_PX = 2400  # widen the page rail so the 160-column terminal renders large

STILLS = (
    ("book.png", 13.5),  # cursor down the streaming book, depth bars and mid
    ("order.png", 19.0),  # the review strip: size, cost, payout, DRY
    ("dryrun.png", 23.0),  # DRY RUN: ... signed, not posted
)


def serve_site() -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def main() -> None:
    port = serve_site()
    url = f"http://127.0.0.1:{port}/index.html"
    UI.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": RAIL_PX + 160, "height": 1400})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        # the page dropped the player; bring the vendored one in and give it a
        # holder of its own, as wide as the rail used to be
        page.add_style_tag(url="assets/asciinema-player.css")
        page.add_script_tag(url="assets/asciinema-player.min.js")
        page.wait_for_function("typeof AsciinemaPlayer !== 'undefined'")
        page.evaluate(
            f"""() => {{
              const holder = document.createElement("div");
              holder.id = "brag-still-holder";
              holder.style.cssText = "position:fixed;top:0;left:0;width:{RAIL_PX}px;z-index:9999;background:#0a0e14";
              document.body.appendChild(holder);
            }}"""
        )
        # a paused player paints its play overlay over the terminal; the stills
        # are product frames, not a player
        page.add_style_tag(
            content=".ap-overlay, .ap-play-button, .ap-control-bar { display: none !important; }"
            " #brag-still-holder .ap-player { background: transparent; }"
        )

        for name, at in STILLS:
            page.evaluate(
                """(at) => {
                  const holder = document.getElementById("brag-still-holder");
                  holder.innerHTML = "";
                  AsciinemaPlayer.create("assets/demo.cast", holder, {
                    autoPlay: false, controls: false, fit: "width",
                    theme: "asciinema", poster: "npt:" + at,
                  });
                }""",
                at,
            )
            page.wait_for_selector(".ap-terminal")
            page.wait_for_timeout(1500)  # font load + poster paint
            box = page.locator(".ap-terminal").bounding_box()
            assert box and box["width"] > 2000, f"terminal did not widen: {box}"
            page.screenshot(path=str(UI / name), full_page=True, clip=box)
            print(name, (UI / name).stat().st_size, "bytes")

        page.close()
        browser.close()


if __name__ == "__main__":
    main()
