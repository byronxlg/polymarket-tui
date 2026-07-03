"""DataTable with arrow-first navigation.

right opens the selected row, left goes back a screen, and up on the first
row raises TopReached so the screen can move focus to whatever sits above
(category bar, chart, search box).
"""

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
        Binding("right", "select_cursor", "open", show=False),
        Binding("left", "app.nav_back", "back", show=False),
    ]

    def action_cursor_up(self) -> None:
        if self.cursor_row == 0 or self.row_count == 0:
            self.post_message(self.TopReached(self))
            return
        super().action_cursor_up()
