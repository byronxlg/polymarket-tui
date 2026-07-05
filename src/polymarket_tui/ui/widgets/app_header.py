"""One-line header: app/screen title left, clock right.

The clock applies the app's NTP-measured offset, so it shows network-true
time (1Hz; the millisecond display was retired with the navy restyle).
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
        self.set_interval(0.5, self._tick)
        self._tick()

    def set_title(self, title: str) -> None:
        self._title = title
        self._tick()

    def _tick(self) -> None:
        offset = getattr(self.app, "ntp_offset", None)
        now = datetime.fromtimestamp(time.time() + (offset or 0.0)).astimezone()
        clock = now.strftime("%a %b %-d  %H:%M:%S")
        if offset is None:
            clock += " (sys)"
        account: Text = getattr(self.app, "account_status", Text(""))
        width = self.size.width
        out = Text(no_wrap=True, overflow="crop")
        out.append(f" {self._title}", style="bold")
        # title ... account strip · clock
        right_len = account.cell_len + 3 + len(clock) + 1
        pad = width - (len(self._title) + 1) - right_len
        if pad > 0:
            out.append(" " * pad)
        out.append_text(account)
        out.append("   ")
        out.append(clock + " ", style="dim")
        self.update(out)
