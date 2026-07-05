"""Serve polymarket-tui in the browser behind a landing page.

`/`      -> a static landing page (web/templates/landing.html)
`/app`   -> the live TUI, streamed to an xterm.js terminal via textual-serve
`/ws`    -> the app websocket (unchanged from textual-serve)

Run with:  uv run polymarket-tui-web   (or  python -m polymarket_tui.web.serve)

The terminal starts in DRY mode like every session; nothing here enables
LIVE trading. Each browser tab spawns its own isolated app subprocess.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import aiohttp_jinja2
import jinja2
import textual_serve.server as _ts
from aiohttp import web
from textual_serve.server import Server

WEB_DIR = Path(__file__).parent.resolve()
LANDING_TEMPLATES = WEB_DIR / "templates"
LANDING_STATIC = WEB_DIR / "static"
TS_TEMPLATES = Path(_ts.__file__).parent / "templates"


class LandingServer(Server):
    """A textual-serve Server that puts a marketing landing page at `/`.

    The terminal that textual-serve normally serves at `/` is moved to
    `/app`; `/` renders our own page instead. Jinja loads templates from
    both our directory and textual-serve's so `app_index.html` still
    resolves for the terminal view.
    """

    async def _make_app(self) -> web.Application:
        app = web.Application()

        # Resolve templates from our dir first, then fall back to
        # textual-serve's (for app_index.html).
        aiohttp_jinja2.setup(
            app,
            loader=jinja2.ChoiceLoader(
                [
                    jinja2.FileSystemLoader(str(LANDING_TEMPLATES)),
                    jinja2.FileSystemLoader(str(TS_TEMPLATES)),
                ]
            ),
        )

        app.add_routes(
            [
                web.get("/", self.handle_landing, name="landing"),
                web.get("/app", self.handle_index, name="index"),
                web.get("/ws", self.handle_websocket, name="websocket"),
                web.get("/download/{key}", self.handle_download, name="download"),
                web.static("/static", self.statics_path, show_index=False, name="static"),
                web.static(
                    "/assets", str(LANDING_STATIC), show_index=False, name="assets"
                ),
            ]
        )
        app.on_startup.append(self.on_startup)
        app.on_shutdown.append(self.on_shutdown)
        return app

    @aiohttp_jinja2.template("landing.html")
    async def handle_landing(self, request: web.Request) -> dict[str, Any]:
        return {"title": self.title}


def main() -> None:
    host = os.environ.get("PMTUI_WEB_HOST", "localhost")
    port = int(os.environ.get("PMTUI_WEB_PORT", "8000"))
    public_url = os.environ.get("PMTUI_WEB_PUBLIC_URL")

    # Launch the app as a module so it works regardless of how the script
    # entry point is installed. -u keeps the pty stream unbuffered.
    command = f"{sys.executable} -u -m polymarket_tui"

    server = LandingServer(
        command=command,
        host=host,
        port=port,
        title="polymarket-tui",
        public_url=public_url,
    )
    server.serve(debug=bool(os.environ.get("PMTUI_WEB_DEBUG")))


if __name__ == "__main__":
    main()
