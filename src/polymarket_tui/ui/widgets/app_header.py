"""One-line header: app/screen title left, millisecond clock right.

The clock ticks at 20Hz and applies the app's NTP-measured offset, so it shows
network-true time to within the terminal's refresh granularity.
"""

from __future__ import annotations

import time
from datetime import datetime

from rich.text import Text
from textual.widgets import Static


class AppHeader(Static):
    DEFAULT_CSS = """
    AppHeader {
        dock: top;
        height: 1;
        background: $panel;
        color: $text;
    }
    """

    def __init__(self, title: str = "polymarket-tui", **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title

    def on_mount(self) -> None:
        self.set_interval(0.05, self._tick)
        self._tick()

    def _tick(self) -> None:
        offset = getattr(self.app, "ntp_offset", None)
        now = datetime.fromtimestamp(time.time() + (offset or 0.0)).astimezone()
        clock = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
        if offset is None:
            clock += " (sys)"
        width = self.size.width
        out = Text()
        out.append(f" {self._title}", style="bold")
        pad = width - len(self._title) - len(clock) - 3
        if pad > 0:
            out.append(" " * pad)
        out.append(clock + " ", style="bold cyan")
        self.update(out)
