"""DataTable with vim-style navigation keys."""

from __future__ import annotations

from textual.binding import Binding
from textual.widgets import DataTable


class VimDataTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "down", show=False),
        Binding("k", "cursor_up", "up", show=False),
        Binding("g", "scroll_top", "top", show=False),
        Binding("G", "scroll_bottom", "bottom", show=False),
        Binding("ctrl+d", "page_down", "half page down", show=False),
        Binding("ctrl+u", "page_up", "half page up", show=False),
        # right/> open the selected row; left/< go back a screen
        Binding("right", "select_cursor", "open", show=False),
        Binding("greater_than_sign", "select_cursor", "open", show=False),
        Binding("left", "app.nav_back", "back", show=False),
        Binding("less_than_sign", "app.nav_back", "back", show=False),
    ]
