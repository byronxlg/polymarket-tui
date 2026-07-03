"""Reusable confirmation modal. Returns True on confirm, False otherwise."""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [
        Binding("enter", "confirm", "confirm"),
        Binding("escape", "dismiss_modal", "cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > Vertical {
        width: 70;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfirmModal #modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    ConfirmModal #modal-actions {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, title: str, body: Text | str, confirm_label: str = "confirm") -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="modal-title")
            yield Static(self._body, id="modal-body")
            yield Static(f"enter {self._confirm_label}   esc cancel", id="modal-actions")

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
