"""PolymarketApp.notify must force markup off, not merely default it.

Toasts carry API/validation error text with '[bracketed]' fragments (a
PolyApiException embeds the HTTP body). Textual parses a notification as markup
by default and crashes on those. The app overrides notify to disable markup -
but Textual's Widget.notify defaults markup=True and forwards it explicitly, so
a screen/widget's self.notify(...) reaches the override with markup already
True. A setdefault was a no-op there; the override must overwrite.

Tested against the real PolymarketApp.notify without bootstrapping the app
(__init__ builds API clients and reads credentials): the method only uses self
to reach super().notify, so an un-initialised instance exercises it faithfully.
"""

from __future__ import annotations

from unittest.mock import patch

from textual.app import App

from polymarket_tui.ui.app import PolymarketApp

BRACKETED = "balance error: PolyApiException[status_code=502, error_message=<!DOCTYPE html>]"


def _capture(markup_kwarg):
    app = object.__new__(PolymarketApp)  # skip __init__ (clients, creds, theme)
    with patch.object(App, "notify") as super_notify:
        app.notify(BRACKETED, markup=markup_kwarg)
    assert super_notify.call_count == 1
    return super_notify.call_args


def test_widget_notify_forwarding_markup_true_is_overridden_to_false():
    # This is the exact hole: Widget.notify forwards markup=True.
    _, kwargs = _capture(markup_kwarg=True)
    assert kwargs["markup"] is False


def test_message_is_passed_through_unchanged():
    args, kwargs = _capture(markup_kwarg=True)
    assert args[0] == BRACKETED


def test_default_direct_app_notify_also_renders_literally():
    # A direct app.notify(...) with no markup kwarg still ends up False.
    app = object.__new__(PolymarketApp)
    with patch.object(App, "notify") as super_notify:
        app.notify(BRACKETED)
    assert super_notify.call_args.kwargs["markup"] is False
