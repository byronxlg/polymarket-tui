"""Event/series comments as a focusable, cursored list.

Comments read like a feed: author + relative time on top, the body wrapped
below. The list carries a row cursor (up/down); right or enter drills into
the highlighted author's profile - the same gesture the trades table uses.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from polymarket_tui.core import fmt
from polymarket_tui.ui.theme import BLUE


class CommentList(OptionList):
    # right mirrors enter: drill into the highlighted author (OptionList already
    # binds up/down/enter). left/esc bubble to the pane, which closes the panel.
    BINDINGS = [Binding("right", "select", "profile", show=False)]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # (address, name) per option, index-aligned with the options; rebuilt
        # wholesale by set_comments so indices stay in sync.
        self._authors: list[tuple[str, str]] = []

    def set_comments(self, comments: list[dict]) -> None:
        self.clear_options()
        self._authors = []
        options: list[Option] = []
        for comment in comments:
            profile = comment.get("profile") or {}
            name = profile.get("name") or profile.get("pseudonym") or "anon"
            address = profile.get("proxyWallet") or comment.get("userAddress") or ""
            self._authors.append((address, name))
            options.append(Option(self._render(comment, name), id=str(len(self._authors) - 1)))
        self.add_options(options)
        if options:
            self.highlighted = 0

    @staticmethod
    def _render(comment: dict, name: str) -> Text:
        out = Text()
        out.append(name, style=f"bold {BLUE}")
        created = str(comment.get("createdAt") or "")
        when = ""
        try:
            when = fmt.ago(datetime.fromisoformat(created.replace("Z", "+00:00")))
        except ValueError:
            pass
        if when:
            out.append(f"  {when}", style="dim")
        reactions = comment.get("reactionCount") or 0
        if reactions:
            out.append(f"  ·  {reactions} {'like' if reactions == 1 else 'likes'}", style="dim")
        body = (comment.get("body") or "").strip()
        if body:
            out.append("\n")
            out.append(body)
        return out

    def author_at_cursor(self) -> tuple[str, str] | None:
        """(address, display name) of the highlighted comment's author."""
        if self.highlighted is None or not self._authors:
            return None
        return self._authors[self.highlighted]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """right/enter drills into the author, like the trades table."""
        event.stop()
        if event.option_index < len(self._authors):
            address, name = self._authors[event.option_index]
            if address:
                self.app.open_user(address, name)
