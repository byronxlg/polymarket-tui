"""Price chart panel: legend line with live prices + smooth line chart.

The legend is rendered outside the plot (a Rich line above it) so the plot area
stays clean; series colors are deterministic so legend and lines always match.

Inspect mode: `x` (bound on the owning screen) focuses the panel and shows a
crosshair; left/right step through time, escape/x exits and returns focus.
"""

from __future__ import annotations

import bisect
from datetime import datetime

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import PricePoint
from polymarket_tui.ui.theme import AMBER, BLUE, DOWN, UP, rgb
from polymarket_tui.ui.widgets.linechart import render_chart

MAX_SERIES = 6

# One palette, used for both the chart lines and the Rich legend swatches.
# The first four derive from the theme constants (an edit there follows
# through here); purple/sky are chart-only fill-ins for series 5-6.
PALETTE: list[tuple[int, int, int]] = [
    rgb(BLUE),
    rgb(AMBER),
    rgb(UP),
    rgb(DOWN),
    (187, 154, 247),  # purple
    (122, 207, 255),  # sky
]

def _rich_color(rgb: tuple[int, int, int]) -> str:
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def _time_format(interval_key: str, span_seconds: float) -> str:
    if interval_key in ("1H", "6H"):
        return "%H:%M"
    if interval_key == "1D":
        # A 1D window usually crosses midnight; disambiguate with the weekday.
        return "%a %H:%M" if span_seconds > 6 * 3600 else "%H:%M"
    return "%b %d"


def _change_text(delta: float) -> tuple[str, str]:
    """(text, style) for a price change in dollars."""
    if abs(delta) < 0.0005:
        return "+0.0c", "dim"
    # Muted UP/DOWN: a change label is context, not a live bid/ask price.
    return fmt.cents(delta, signed=True), (f"dim {UP}" if delta > 0 else f"dim {DOWN}")


class PriceChartPanel(Vertical):
    """Legend + chart. Call show(series, interval_key) with (label, points) tuples."""

    BINDINGS = [
        Binding("left", "step(-1)", "back", show=False),
        Binding("right", "step(1)", "forward", show=False),
        Binding("shift+left", "step(-10)", "back 10", show=False),
        Binding("shift+right", "step(10)", "forward 10", show=False),
        Binding("escape", "exit_inspect", "exit inspect", show=False),
        Binding("x", "exit_inspect", "exit inspect", show=False),
        Binding("down", "exit_inspect", "exit inspect", show=False),
        Binding("up", "exit_inspect", "exit inspect", show=False),
    ]

    DEFAULT_CSS = """
    PriceChartPanel > #chart-legend {
        height: 1;
        padding: 0 1;
    }
    PriceChartPanel > #chart-canvas {
        height: 1fr;
    }
    PriceChartPanel:focus-within #chart-legend {
        background: $panel;
    }
    """

    can_focus = False  # focusable only while inspecting

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._series: list[tuple[str, list[PricePoint]]] = []
        self._interval = "1D"
        self._inspect_ts: int | None = None  # crosshair time, None = live mode
        self._return_focus: Widget | None = None

    def compose(self):
        yield Static(id="chart-legend")
        yield Static(id="chart-canvas")

    def on_resize(self) -> None:
        self._draw_plot()

    def show(self, series: list[tuple[str, list[PricePoint]]], interval_key: str) -> None:
        self._series = [(label, pts) for label, pts in series if pts][:MAX_SERIES]
        self._interval = interval_key
        if self._inspect_ts is not None or self.has_focus:
            # New data invalidates the crosshair position - leave inspect cleanly.
            self.action_exit_inspect()
            return
        self._redraw()

    def _redraw(self) -> None:
        self._draw_legend()
        self._draw_plot()

    # -- inspect mode -------------------------------------------------------------

    @property
    def _lead_times(self) -> list[int]:
        return [p.t for p in self._series[0][1]] if self._series else []

    def enter_inspect(self, return_focus: Widget | None = None) -> None:
        if not self._series:
            return
        self._return_focus = return_focus
        self.can_focus = True
        self.focus()
        # Start inside the plot (not at the right edge, where the crosshair
        # would blend into the frame border).
        times = self._lead_times
        self._inspect_ts = times[max(0, int(len(times) * 0.85) - 1)]
        self._redraw()

    def action_exit_inspect(self) -> None:
        self._inspect_ts = None
        self.can_focus = False
        self._redraw()
        if self._return_focus is not None and self._return_focus.is_mounted:
            self._return_focus.focus()
        else:
            self.screen.set_focus(None)

    def action_step(self, delta: int) -> None:
        times = self._lead_times
        if not times or self._inspect_ts is None:
            return
        # Scale steps to the window so each press moves visibly: ~1.5% per
        # arrow press, ~10% per shift press (delta arrives as +-1 / +-10).
        unit = max(1, len(times) // 66)
        idx = bisect.bisect_left(times, self._inspect_ts)
        idx = max(0, min(len(times) - 1, idx + delta * unit))
        self._inspect_ts = times[idx]
        self._redraw()

    def _value_at(self, points: list[PricePoint], ts: int) -> PricePoint:
        idx = bisect.bisect_left([p.t for p in points], ts)
        idx = max(0, min(len(points) - 1, idx))
        return points[idx]

    # -- legend -----------------------------------------------------------------

    def _draw_legend(self) -> None:
        legend = self.query_one("#chart-legend", Static)
        if not self._series:
            legend.update(Text("no price history", style="dim"))
            return
        out = Text()
        inspecting = self._inspect_ts is not None
        if inspecting:
            when = datetime.fromtimestamp(self._inspect_ts).astimezone()
            out.append(when.strftime("%b %d %H:%M "), style="bold reverse")
            out.append(" ")
        for i, (label, points) in enumerate(self._series):
            color = _rich_color(PALETTE[i % len(PALETTE)])
            if i:
                out.append("   ")
            out.append("● ", style=color)
            out.append(fmt.trunc(label, 22), style=color)
            if inspecting:
                point = self._value_at(points, self._inspect_ts)
                out.append(f" {fmt.cents(point.p)}", style=f"bold {color}")
            else:
                out.append(f" {fmt.cents(points[-1].p)}", style=f"bold {color}")
                # Change over the visible window.
                delta = points[-1].p - points[0].p
                text, style = _change_text(delta)
                out.append(f" {text}", style=style)
        if inspecting:
            out.append("   (left/right step, esc exit)", style="dim")
        legend.update(out)

    # -- plot -------------------------------------------------------------------

    def _draw_plot(self) -> None:
        canvas = self.query_one("#chart-canvas", Static)
        if not self._series:
            canvas.update(Text(""))
            return
        size = canvas.size
        if size.width < 12 or size.height < 5:
            return
        span = max(p.t for _, pts in self._series for p in pts[-1:]) - min(
            pts[0].t for _, pts in self._series
        )
        canvas.update(
            render_chart(
                [
                    (points, PALETTE[i % len(PALETTE)])
                    for i, (_label, points) in enumerate(self._series)
                ],
                width=size.width,
                height=size.height,
                time_format=_time_format(self._interval, span),
                inspect_ts=self._inspect_ts,
            )
        )
