"""DataTable with vim-style navigation keys and spatial arrow escape."""

from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable


class VimDataTable(DataTable):
    class TopReached(Message):
        """Up pressed while already on the first row - focus whatever is above."""

        def __init__(self, table: VimDataTable) -> None:
            super().__init__()
            self.table = table

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

    def action_cursor_up(self) -> None:
        if self.cursor_row == 0 or self.row_count == 0:
            self.post_message(self.TopReached(self))
            return
        super().action_cursor_up()
