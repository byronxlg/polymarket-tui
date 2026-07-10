"""Closed-positions table, shared by the portfolio and the trader profile.

Polymarket delists a market from Gamma once it resolves - `/markets?slug=` and
`/markets?condition_ids=` both answer `[]` - so enter cannot drill into most
settled positions. The web page survives, so `o` opens it. The binding lives on
the table (not the pane) so the footer only advertises it here.
"""

from __future__ import annotations

from textual.binding import Binding

from polymarket_tui.core.links import open_and_copy
from polymarket_tui.ui.widgets.vim_table import VimDataTable


class ClosedTable(VimDataTable):
    BINDINGS = [Binding("o", "open_on_web", "open on web")]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # row key -> polymarket.com url. Rebuilt with every render, because a
        # refit rebuilds the rows.
        self._web_urls: dict[str, str] = {}

    def set_web_urls(self, urls: dict[str, str]) -> None:
        self._web_urls = urls
        self.refresh_bindings()  # the o hint gates on having a url

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Nothing settled - nothing to open."""
        if action == "open_on_web" and self.row_count == 0:
            return False
        return super().check_action(action, parameters)

    def action_open_on_web(self) -> None:
        if self.cursor_row is None or self.row_count == 0:
            return
        row_key = self.coordinate_to_cell_key((self.cursor_row, 0)).row_key
        url = self._web_urls.get(str(row_key.value), "")
        if not url:
            self.notify("No web URL for this position", severity="warning")
            return
        self.notify(open_and_copy(url), timeout=6)
