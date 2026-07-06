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

    BINDINGS = [
        Binding("right", "select_cursor", "open", show=False),
        Binding("left", "app.nav_back", "back", show=False),
    ]

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """An empty table has nothing to open - don't advertise enter/right.
        Subclasses that make enter visible in the footer inherit the gate."""
        if action == "select_cursor" and self.row_count == 0:
            return False
        return True

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
