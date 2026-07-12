"""fmt.error_brief: a short, single-line, markup-safe error for status lines.

An API 502 embeds its whole HTML response body in the exception message. That
dump crashed the app (its '[' broke Rich markup when the balance line rendered
the string as markup) and was useless in a one-line field even when it didn't.
"""

from __future__ import annotations

import httpx

from polymarket_tui.core import fmt


class _ApiErr(Exception):
    """Mimics py_clob_client_v2.PolyApiException: status_code + error_msg, and a
    repr that embeds the raw body."""

    def __init__(self, status_code, error_msg):
        self.status_code = status_code
        self.error_msg = error_msg

    def __str__(self):
        return f"_ApiErr[status_code={self.status_code}, error_message={self.error_msg}]"


def test_status_code_collapses_a_huge_html_body_to_one_token():
    huge = "<!DOCTYPE html>\n<html>" + "x" * 6000 + "</html>"
    assert fmt.error_brief(_ApiErr(502, huge)) == "HTTP 502"


def test_real_poly_api_exception_502():
    from py_clob_client_v2.exceptions import PolyApiException

    resp = httpx.Response(status_code=502, text="<!DOCTYPE html>" + "x" * 6000)
    assert fmt.error_brief(PolyApiException(resp=resp)) == "HTTP 502"


def test_message_field_preferred_over_the_noisy_repr():
    # status_code None -> fall through, but use error_msg, not the bracket repr.
    assert fmt.error_brief(_ApiErr(None, "not enough balance")) == "not enough balance"


def test_plain_exception_uses_its_first_line_collapsed():
    assert fmt.error_brief(ValueError("bad thing\nstack detail")) == "bad thing"


def test_whitespace_is_collapsed():
    assert fmt.error_brief(ValueError("too    many   spaces")) == "too many spaces"


def test_empty_message_falls_back_to_the_class_name():
    assert fmt.error_brief(RuntimeError()) == "RuntimeError"


def test_long_plain_message_is_truncated_with_an_ellipsis():
    out = fmt.error_brief(ValueError("z" * 200), width=40)
    assert len(out) == 40
    assert out.endswith("…")


def test_result_is_a_plain_str_safe_to_wrap_in_text():
    # The contract the fix relies on: a str the caller wraps in rich.text.Text.
    assert isinstance(fmt.error_brief(_ApiErr(500, "x")), str)
