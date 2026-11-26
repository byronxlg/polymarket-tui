# ruff: noqa: E501  (long lines are the JavaScript probes each check evaluates)
"""Walk the landing page in WebKit (the Safari engine) and capture every state.

    uv run --with playwright python scripts/site_walk.py [path-under-site] [out-dir]

Serves site/ locally, drives the page at phone width first, then rotated and
at desktop width, and writes one PNG per state plus a pass/fail line per check
(docs/ux/landing.md: control states and paths). Exits non-zero on any failure.
"""
from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parent.parent / "site"
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
STUB_OK = "window.__copied=[];navigator.clipboard.writeText=function(t){window.__copied.push(t);return Promise.resolve()};"
STUB_FAIL = "navigator.clipboard.writeText=function(){return Promise.reject(new Error('refused'))};"
fails: list[str] = []


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("pass " if ok else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""))
    if not ok:
        fails.append(name)


def no_overflow(pg, name: str) -> None:
    w = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(f"{name}: no sideways scroll", w[0] <= w[1], w)


def main() -> int:
    sub = sys.argv[1] if len(sys.argv) > 1 else "next/"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "site-walk")
    out.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(Quiet, directory=str(SITE))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/{sub}"

    with sync_playwright() as p:
        b = p.webkit.launch()

        # Phone, at rest.
        c = b.new_context(**PHONE)
        c.add_init_script(STUB_OK)
        pg = c.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("requestfailed", lambda r: errors.append("failed " + r.url))
        pg.goto(url, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(800)
        pg.screenshot(path=out / "01-rest-first-screen.png")
        pg.evaluate("[].forEach.call(document.images,function(i){i.loading='eager'})")
        pg.wait_for_timeout(500)
        pg.screenshot(path=out / "02-rest-full.png", full_page=True)
        no_overflow(pg, "rest")
        check("font loaded", pg.evaluate("document.fonts.check('600 32px \"Mona Sans\"')"))
        check("install line on the first screen (Safari with its bars: 660px)", pg.evaluate("document.querySelector('#install .cmd').getBoundingClientRect().bottom") < 660)
        check("uv command on one line, not clipped", pg.evaluate("(function(){var e=document.querySelector('#install .panel:not([hidden]) pre');return e.scrollWidth<=e.clientWidth&&e.getBoundingClientRect().height<40})()"))
        check("recording playing", pg.evaluate("!document.getElementById('rec').paused"))
        check("recording button says Pause", pg.inner_text("#rec-btn") == "Pause")
        small = pg.evaluate("[].filter.call(document.querySelectorAll('a,button'),function(e){var r=e.getBoundingClientRect();return r.width&&e.id!=='rec-btn'&&(r.height<44||r.width<44)}).map(function(e){return e.textContent.trim()||e.className})")
        check("touch targets at least 44px", not small, small)
        check("safety line on the first screen", pg.evaluate("document.querySelector('.safe').getBoundingClientRect().bottom") < 660)
        check("pause button hit area at least 44px", pg.evaluate("parseFloat(getComputedStyle(document.getElementById('rec-btn'),'::before').height)") >= 44)

        # Copy: pressed, done, double tap, back to rest.
        copy = pg.locator("#install .panel:not([hidden]) .copy")
        box = copy.bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.mouse.down()
        pg.wait_for_timeout(200)
        pg.screenshot(path=out / "03-copy-pressed.png")
        check("copy pressed shrinks", "matrix(0.97" in pg.evaluate("getComputedStyle(document.querySelector('#install .panel:not([hidden]) .copy')).transform"))
        pg.mouse.up()
        pg.wait_for_timeout(300)
        pg.screenshot(path=out / "04-copy-done.png")
        check("copy done state", copy.get_attribute("data-state") == "done")
        check("copied the uv command", pg.evaluate("window.__copied") == ["uv tool install polymarket-tui"])
        check("copy announced", pg.inner_text("#said") == "Copied")
        copy.click()
        copy.click()
        pg.wait_for_timeout(1500)
        check("double tap keeps done", copy.get_attribute("data-state") == "done")
        pg.wait_for_timeout(900)
        check("copy returns to rest after 2s", copy.get_attribute("data-state") == "rest")

        # Tabs.
        for i, name in enumerate(["uv", "Homebrew", "curl", "git"]):
            tab = pg.locator("#install .tab").nth(i)
            if i == 1:
                copy.click()  # leave "Copied" showing, then change tab
            tab.click()
            pg.wait_for_timeout(150)
            pg.screenshot(path=out / f"05-tab-{name}.png")
            check(f"tab {name} selected in both boxes", pg.evaluate(f"[].every.call(document.querySelectorAll('[data-install]'),function(b){{return b.querySelectorAll('.tab')[{i}].getAttribute('aria-selected')==='true'&&!b.querySelectorAll('.panel')[{i}].hidden}})"))
            check(f"tab {name}: copy at rest", pg.evaluate("[].every.call(document.querySelectorAll('.copy'),function(b){return b.dataset.state==='rest'})"))
            no_overflow(pg, f"tab {name}")
            check(f"tab {name}: whole command readable", pg.evaluate("(function(){var e=document.querySelector('#install .panel:not([hidden]) pre');return e.scrollWidth<=e.clientWidth+1})()"))
        tb = pg.locator("#install .tab").nth(2).bounding_box()
        pg.mouse.move(tb["x"] + 10, tb["y"] + 10)
        pg.mouse.down()
        pg.wait_for_timeout(150)
        pg.screenshot(path=out / "06-tab-pressed.png")
        pg.mouse.up()
        pg.locator("#install .tab").nth(3).click()
        pg.locator("#install .panel:not([hidden]) .copy").click()
        check("git copies both lines", "\n" in pg.evaluate("window.__copied.slice(-1)[0]"))

        # Recording button.
        pg.locator("#rec-btn").click()
        pg.wait_for_timeout(200)
        check("pause stops the recording", pg.evaluate("document.getElementById('rec').paused") and pg.inner_text("#rec-btn") == "Play")
        pg.screenshot(path=out / "07-recording-paused.png")

        # Old links still land somewhere.
        for anchor in ["install", "features", "keys", "access", "blog"]:
            pg.goto(url + "#" + anchor)
            pg.wait_for_timeout(250)
            top = pg.evaluate(f"document.getElementById('{anchor}').getBoundingClientRect().top")
            check(f"#{anchor} lands in view, clear of the bar", 56 <= top < 844, round(top))
        pg.screenshot(path=out / "08-anchor-blog-footer.png")
        check("no page errors", not errors, errors)
        c.close()

        # Clipboard refused.
        c = b.new_context(**PHONE)
        c.add_init_script(STUB_FAIL)
        pg = c.new_page()
        pg.goto(url, wait_until="networkidle")
        pg.locator("#install .panel:not([hidden]) .copy").click()
        pg.wait_for_timeout(350)
        pg.screenshot(path=out / "09-copy-failed.png")
        check("copy failed state and announcement", pg.locator("#install .panel:not([hidden]) .copy").get_attribute("data-state") == "failed" and pg.inner_text("#said") == "Copy failed")
        no_overflow(pg, "copy failed")
        pg.wait_for_timeout(2100)
        check("failed returns to rest", pg.locator("#install .panel:not([hidden]) .copy").get_attribute("data-state") == "rest")
        c.close()

        # Reduced motion.
        c = b.new_context(**PHONE, reduced_motion="reduce")
        pg = c.new_page()
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(500)
        check("reduced motion: recording paused, button says Play", pg.evaluate("document.getElementById('rec').paused") and pg.inner_text("#rec-btn") == "Play")
        pg.screenshot(path=out / "10-reduced-motion.png")
        c.close()

        # No scripts.
        c = b.new_context(**PHONE, java_script_enabled=False)
        pg = c.new_page()
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(300)
        pg.screenshot(path=out / "11-no-scripts-full.png", full_page=True)
        c.close()

        # Recording blocked (offline, Low Power Mode): poster holds the space.
        c = b.new_context(**PHONE)
        pg = c.new_page()
        pg.route("**/brag.mp4", lambda r: r.abort())
        pg.goto(url, wait_until="load")
        pg.wait_for_timeout(800)
        pg.screenshot(path=out / "12-recording-blocked.png")
        check("recording blocked: install line present, poster holds the space", pg.evaluate("document.querySelector('#install .cmd').getBoundingClientRect().bottom<844 && Math.round(document.getElementById('rec').getBoundingClientRect().height)===175"))
        check("recording blocked: button says Play", pg.inner_text("#rec-btn") == "Play")
        c.close()

        # Rotated phone, then desktop.
        c = b.new_context(viewport={"width": 844, "height": 390}, device_scale_factor=3, is_mobile=True, has_touch=True)
        pg = c.new_page()
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(500)
        no_overflow(pg, "rotated")
        check("rotated: install line on the first screen", pg.evaluate("document.querySelector('#install .cmd').getBoundingClientRect().bottom") < 390)
        pg.screenshot(path=out / "13-rotated.png")
        c.close()
        c = b.new_context(viewport={"width": 1280, "height": 800})
        pg = c.new_page()
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(600)
        no_overflow(pg, "desktop")
        check("desktop: install line on the first screen", pg.evaluate("document.querySelector('#install .cmd').getBoundingClientRect().bottom") < 800)
        pg.screenshot(path=out / "14-desktop-first-screen.png")
        pg.evaluate("[].forEach.call(document.images,function(i){i.loading='eager'})")
        pg.wait_for_timeout(500)
        pg.screenshot(path=out / "15-desktop-full.png", full_page=True)
        pg.keyboard.press("Tab")
        pg.keyboard.press("Tab")
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(150)
        check("keyboard: arrow moves the tab", pg.evaluate("document.activeElement.textContent") == "Homebrew")
        pg.screenshot(path=out / "16-desktop-keyboard-focus.png")
        c.close()
        b.close()
    srv.shutdown()
    print(f"{len(fails)} failed" if fails else "all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
