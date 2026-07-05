"""DataTable with arrow-first navigation.

right opens the selected row, left goes back a screen, and up on the first
row raises TopReached so the screen can move focus to whatever sits above
(category bar, chart, search box).

Tables built with open_on_right=False instead raise RightReached on right, so
the hosting screen can step the cursor sideways into an adjacent panel rather
than opening the row.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable


class VimDataTable(DataTable):
    def add_column(self, label, **kwargs):
        # Uppercase headers everywhere (navy restyle); styling is CSS's job.
        if isinstance(label, str):
            label = label.upper()
        return super().add_column(label, **kwargs)

    class TopReached(Message):
        """Up pressed while already on the first row - focus whatever is above."""

        def __init__(self, table: VimDataTable) -> None:
            super().__init__()
            self.table = table

    class BottomReached(Message):
        """Down pressed on the last row - focus whatever sits below."""

        def __init__(self, table: VimDataTable) -> None:
            super().__init__()
            self.table = table

    class RightReached(Message):
        """Right pressed on a table that doesn't open rows - step sideways."""

        def __init__(self, table: VimDataTable) -> None:
            super().__init__()
            self.table = table

    BINDINGS = [
        Binding("right", "cursor_right", "open", show=False),
        Binding("left", "app.nav_back", "back", show=False),
    ]

    def __init__(self, *args, open_on_right: bool = True, **kwargs) -> None:
        self.open_on_right = open_on_right
        super().__init__(*args, **kwargs)

    def action_cursor_up(self) -> None:
        if self.cursor_row == 0 or self.row_count == 0:
            self.post_message(self.TopReached(self))
            return
        super().action_cursor_up()

    def action_cursor_down(self) -> None:
        if self.row_count == 0 or self.cursor_row == self.row_count - 1:
            self.post_message(self.BottomReached(self))
            return
        super().action_cursor_down()

    def action_cursor_right(self) -> None:
        if self.open_on_right:
            self.action_select_cursor()
        else:
            self.post_message(self.RightReached(self))
