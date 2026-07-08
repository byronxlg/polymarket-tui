"""Column fitting: the flex column fills the pane by default (never clips)."""

from __future__ import annotations

from polymarket_tui.ui.tiers import columns_need, fit_columns


def _cols() -> tuple[tuple[str, str, int], ...]:
    return (("title", "Title", 20), ("price", "Price", 6))


def test_omitting_flex_max_fills_the_width() -> None:
    # A table that forgets to measure its longest cell must still fill the
    # pane, not clip text at the fixed tier width while space sits empty.
    cols = _cols()
    width = columns_need(cols) + 40  # 40 cells of surplus
    fitted = {k: w for k, _, w in fit_columns(cols, width, "title")}
    assert fitted["title"] == 20 + 40  # grew into the whole surplus
    assert fitted["price"] == 6  # numeric column untouched


def test_flex_max_caps_growth_at_content() -> None:
    cols = _cols()
    width = columns_need(cols) + 40
    fitted = {k: w for k, _, w in fit_columns(cols, width, "title", flex_max=25)}
    assert fitted["title"] == 25  # stops at the longest actual cell
    assert fitted["price"] == 6


def test_deficit_shrinks_flex_to_floor() -> None:
    cols = _cols()
    width = columns_need(cols) - 100  # far too narrow
    fitted = {k: w for k, _, w in fit_columns(cols, width, "title")}
    assert fitted["title"] == 14  # floor, never below
    assert fitted["price"] == 6


def test_exact_fit_leaves_columns_unchanged() -> None:
    cols = _cols()
    assert fit_columns(cols, columns_need(cols), "title") == list(cols)
