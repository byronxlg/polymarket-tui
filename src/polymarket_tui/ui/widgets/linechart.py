"""Smooth terminal line charts with box-drawing characters.

Renders multi-series price history as continuous lines (╭─╮╰│╯) instead of
plotext's braille dot patterns. Series are resampled onto a shared time grid,
so differently-shaped histories align. Returns a Rich Text ready for a Static.
"""

from __future__ import annotations

import bisect
from datetime import datetime

from rich.text import Text

from polymarket_tui.models.market import PricePoint

GUTTER = 7  # "  33.5┤"
RGB = tuple[int, int, int]

CROSSHAIR_BG = " on grey30"


def _color(rgb: RGB) -> str:
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def _resample(points: list[PricePoint], lo_t: int, hi_t: int, width: int) -> list[float | None]:
    """Value per column via last-known-price (step) sampling; None before start."""
    times = [p.t for p in points]
    values: list[float | None] = []
    for i in range(width):
        t = lo_t + (hi_t - lo_t) * i / max(1, width - 1)
        idx = bisect.bisect_right(times, t) - 1
        values.append(points[idx].p * 100 if idx >= 0 else None)
    return values


def render_chart(
    series: list[tuple[list[PricePoint], RGB]],
    width: int,
    height: int,
    time_format: str,
    inspect_ts: int | None = None,
    clamp: tuple[float, float] | None = (0.0, 100.0),
) -> Text:
    plot_w = width - GUTTER
    rows = height - 1  # bottom row is the time axis
    if plot_w < 10 or rows < 4 or not series:
        return Text("")

    lo_t = min(pts[0].t for pts, _ in series)
    hi_t = max(pts[-1].t for pts, _ in series)
    sampled = [(_resample(pts, lo_t, hi_t, plot_w), color) for pts, color in series]

    all_values = [v for vals, _ in sampled for v in vals if v is not None]
    if not all_values:
        return Text("")
    lo_y, hi_y = min(all_values), max(all_values)
    # Scale to the data (like the web chart). A fixed minimum window would
    # squash penny markets into a sliver; a small floor keeps one flat line
    # from filling the whole plot with noise.
    pad = max((hi_y - lo_y) * 0.12, 0.6)
    lo_y, hi_y = lo_y - pad, hi_y + pad
    if clamp is not None:
        lo_y, hi_y = max(clamp[0], lo_y), min(clamp[1], hi_y)
    span = hi_y - lo_y or 1.0

    def to_row(value: float) -> int:
        return round((hi_y - value) / span * (rows - 1))

    # cell buffers: char + color per (row, col)
    chars = [[" "] * plot_w for _ in range(rows)]
    colors: list[list[str | None]] = [[None] * plot_w for _ in range(rows)]

    def put(row: int, col: int, char: str, style: str) -> None:
        if 0 <= row < rows and 0 <= col < plot_w:
            chars[row][col] = char
            colors[row][col] = style

    # Draw follower series first so the lead series ends up on top.
    for values, rgb in reversed(sampled):
        style = _color(rgb)
        prev_row: int | None = None
        for col, value in enumerate(values):
            if value is None:
                prev_row = None
                continue
            row = to_row(value)
            if prev_row is None or prev_row == row:
                put(row, col, "─", style)
            elif row < prev_row:  # price up = row index decreases
                put(prev_row, col, "╯", style)
                put(row, col, "╭", style)
                for between in range(row + 1, prev_row):
                    put(between, col, "│", style)
            else:  # price down
                put(prev_row, col, "╮", style)
                put(row, col, "╰", style)
                for between in range(prev_row + 1, row):
                    put(between, col, "│", style)
            prev_row = row
        # end-of-line marker at the newest sample
        last_cols = [c for c, v in enumerate(values) if v is not None]
        if last_cols:
            col = last_cols[-1]
            put(to_row(values[col]), col, "●", f"bold {style}")

    # crosshair column
    inspect_col: int | None = None
    if inspect_ts is not None and hi_t > lo_t:
        inspect_col = round((inspect_ts - lo_t) / (hi_t - lo_t) * (plot_w - 1))
        inspect_col = max(0, min(plot_w - 1, inspect_col))
        for row in range(rows):
            if chars[row][inspect_col] == " ":
                chars[row][inspect_col] = "│"
                colors[row][inspect_col] = "grey58"

    # y-axis labels on ~5 rows
    label_rows = {0, rows // 4, rows // 2, 3 * rows // 4, rows - 1}
    out = Text(no_wrap=True, overflow="crop")
    for row in range(rows):
        if row in label_rows:
            value = hi_y - row / (rows - 1) * span
            out.append(f"{value:5.1f}┤", style="dim")
        else:
            out.append(" " * 5 + "│", style="dim")
        out.append(" ")
        col = 0
        while col < plot_w:
            style = colors[row][col]
            # batch consecutive same-style cells for fewer segments
            run_start = col
            while col < plot_w and colors[row][col] == style:
                col += 1
            segment = "".join(chars[row][run_start:col])
            if inspect_col is not None and run_start <= inspect_col < col and style:
                # split the run to add the crosshair background on one cell
                pre = segment[: inspect_col - run_start]
                mid = segment[inspect_col - run_start]
                post = segment[inspect_col - run_start + 1 :]
                if pre:
                    out.append(pre, style=style)
                out.append(mid, style=(style or "") + CROSSHAIR_BG)
                if post:
                    out.append(post, style=style)
            else:
                out.append(segment, style=style)
        out.append("\n")

    # time axis
    out.append(" " * 6, style="dim")
    n_labels = max(2, min(6, plot_w // 24))
    axis = [" "] * plot_w
    for i in range(n_labels):
        col = round(i * (plot_w - 1) / (n_labels - 1))
        t = lo_t + (hi_t - lo_t) * col / max(1, plot_w - 1)
        label = datetime.fromtimestamp(t).astimezone().strftime(time_format)
        start = min(max(0, col - len(label) // 2), plot_w - len(label))
        for j, ch in enumerate(label):
            axis[start + j] = ch
    out.append("".join(axis), style="dim")
    return out
