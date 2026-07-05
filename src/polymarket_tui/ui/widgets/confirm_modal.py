"""Reusable confirmation modal. Returns True on confirm, False otherwise.

`tone` colors the border and title chip by severity: "accent" (default)
for neutral confirms, "warn" for check-first prompts, "danger" for
real-money or destructive ones (going LIVE, clearing credentials).
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from polymarket_tui.ui.theme import AMBER, BLUE, DOWN
from polymarket_tui.ui.widgets.order_details import action_hints

TONE_COLORS = {"accent": BLUE, "warn": AMBER, "danger": DOWN}


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [
        Binding("enter", "confirm", "confirm"),
        Binding("escape", "dismiss_modal", "cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
        background: $background 40%;
    }
    ConfirmModal > Vertical {
        width: 70;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfirmModal.tone-warn > Vertical {
        border: round $warning;
    }
    ConfirmModal.tone-danger > Vertical {
        border: round $error;
    }
    ConfirmModal #modal-title {
        margin-bottom: 1;
    }
    ConfirmModal #modal-actions {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title: str,
        body: Text | str,
        confirm_label: str = "confirm",
        tone: str = "accent",
    ) -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._confirm_label = confirm_label
        self._tone = tone if tone in TONE_COLORS else "accent"

    def compose(self) -> ComposeResult:
        self.add_class(f"tone-{self._tone}")
        with Vertical():
            yield Static(
                Text(self._title, style=f"bold {TONE_COLORS[self._tone]}"),
                id="modal-title",
            )
            yield Static(self._body, id="modal-body")
            yield Static(
                action_hints(("enter", self._confirm_label), ("esc", "cancel")),
                id="modal-actions",
            )

    ARM_DELAY_S = 0.35

    def on_mount(self) -> None:
        # Arm after a short delay so an Enter queued from the previous screen
        # (e.g. double-Enter on an input) cannot instantly confirm.
        self._armed_at = time.monotonic() + self.ARM_DELAY_S

    def action_confirm(self) -> None:
        if time.monotonic() < getattr(self, "_armed_at", 0.0):
            return
        self.dismiss(True)

    def action_dismiss_modal(self) -> None:
        self.dismiss(False)
