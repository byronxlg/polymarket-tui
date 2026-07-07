"""Comments or rules in a reading pop-out.

A dead-end lookup, not a navigation level (mirrors RelatedModal): read the
thread or the resolution rules, then esc drops back exactly where you were,
trail untouched. Both were inline panels that stole the chart strip (comments)
or the preview rail (rules); a pop-out gives them the full width and leaves the
book and chart in place.

Comments are a cursored list - right/enter opens the highlighted author's
profile, which pops this modal and drills to them (open_user resets overlays).
Rules are a scrollable text block.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from polymarket_tui.models.market import Event
from polymarket_tui.ui.widgets.comment_list import CommentList
from polymarket_tui.ui.widgets.order_details import action_hints


class ReaderModal(ModalScreen[None]):
    """A focused read - event comments or market/event rules - in a pop-out."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "close"),
        # Modal screens cut the binding chain, so the app's global R can't
        # reach us - rebind it locally so refresh-anywhere still reloads.
        Binding("R", "refresh", "refresh", show=False, key_display="R"),
    ]

    DEFAULT_CSS = """
    ReaderModal {
        align: center middle;
        background: $background 40%;
    }
    ReaderModal > Vertical {
        width: 80%;
        max-width: 120;
        height: 80%;
        border: round $primary;
        background: $surface;
        padding: 0 1 0 1;
    }
    ReaderModal #reader-scroll {
        height: 1fr;
    }
    ReaderModal #reader-body {
        padding: 0 1;
    }
    ReaderModal CommentList {
        height: 1fr;
        background: transparent;
        border: none;
        padding: 0;
        scrollbar-size-vertical: 1;
    }
    ReaderModal CommentList > .option-list--option {
        padding: 0 1 1 1;
    }
    ReaderModal CommentList > .option-list--option-highlighted {
        background: $primary 8%;
    }
    ReaderModal CommentList:focus > .option-list--option-highlighted {
        background: $primary 18%;
        /* Same tint-only cursor as the tables (app.tcss .datatable--cursor):
           neutralize Textual's default block-cursor foreground, which is a
           near-black on some themes and inverts the comment body over our
           faint tint. The author name keeps its own blue span colour. */
        color: $foreground;
        text-style: none;
    }
    ReaderModal #reader-hints {
        height: 1;
        padding: 0 1;
    }
    """

    @classmethod
    def comments(cls, event: Event) -> ReaderModal:
        return cls(kind="comments", event=event, title=f"COMMENTS - {event.title.strip()}")

    @classmethod
    def rules(cls, title: str, body: str) -> ReaderModal:
        return cls(kind="rules", title=title, body=body)

    def __init__(
        self,
        *,
        kind: str,
        event: Event | None = None,
        title: str = "",
        body: str = "",
    ) -> None:
        super().__init__()
        self._kind = kind
        self._event = event
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, classes="screen-title", id="reader-title")
            if self._kind == "comments":
                yield Static(Text("loading...", style="dim"), id="reader-status")
                yield CommentList(id="reader-comments")
                hints = action_hints(("up/down", "move"), ("right", "profile"), ("esc", "close"))
            else:
                body = self._body.strip() or "no rules provided"
                yield VerticalScroll(
                    Static(Text(body, style="dim"), id="reader-body"), id="reader-scroll"
                )
                hints = action_hints(("up/down", "scroll"), ("esc", "close"))
            yield Static(hints, id="reader-hints")

    def on_mount(self) -> None:
        if self._kind == "comments":
            self.query_one("#reader-comments", CommentList).display = False
            self.load_comments()
        else:
            # A focusable scroll container takes the arrow keys for the rules
            # text (VerticalScroll only consumes arrows when it can focus).
            scroll = self.query_one("#reader-scroll", VerticalScroll)
            scroll.can_focus = True
            scroll.focus()

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_refresh(self) -> None:
        """The global R reloads the comment thread in place."""
        if self._kind == "comments":
            self.load_comments()

    @work(exclusive=True)
    async def load_comments(self) -> None:
        event = self._event
        if event is None or not event.id:
            self._status("comments live on the event - none linked here")
            return
        # Recurring/grouped events (Fed, daily Bitcoin, World Cup matches) thread
        # their comments on the series, not the daily event; standalone events
        # keep them on the event itself. See GammaClient.comments.
        series = event.primary_series
        try:
            if series and series.id:
                comments = await self.app.gamma.comments(series.id, entity_type="Series")
            else:
                comments = await self.app.gamma.comments(event.id)
        except Exception as exc:
            self._status(f"comments unavailable: {exc}")
            return
        if not self.is_mounted:
            return  # dismissed while the lookup was in flight
        if not comments:
            self._status("no comments yet")
            return
        clist = self.query_one("#reader-comments", CommentList)
        self.query_one("#reader-status", Static).display = False
        clist.display = True
        clist.set_comments(comments)
        clist.focus()

    def _status(self, message: str) -> None:
        if not self.is_mounted:
            return
        self.query_one("#reader-comments", CommentList).display = False
        status = self.query_one("#reader-status", Static)
        status.display = True
        status.update(Text(message, style="dim"))
