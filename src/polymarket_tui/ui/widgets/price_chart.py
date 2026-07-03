"""Price chart panel: legend line with live prices + plotext chart.

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
from textual_plotext import PlotextPlot

from polymarket_tui.core import fmt
from polymarket_tui.models.market import PricePoint

MAX_SERIES = 6

# One palette, used for both the plotext lines and the Rich legend swatches.
PALETTE: list[tuple[int, int, int]] = [
    (0, 187, 255),  # sky blue
    (255, 155, 66),  # orange
    (46, 204, 113),  # green
    (231, 76, 60),  # red
    (187, 134, 252),  # purple
    (241, 196, 15),  # yellow
]

CROSSHAIR_COLOR = (120, 120, 120)


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
    return fmt.cents(delta, signed=True), ("green" if delta > 0 else "red")


class PriceChartPanel(Vertical):
    """Legend + chart. Call show(series, interval_key) with (label, points) tuples."""

    BINDINGS = [
        Binding("left", "step(-1)", "back", show=False),
        Binding("right", "step(1)", "forward", show=False),
        Binding("shift+left", "step(-10)", "back 10", show=False),
        Binding("shift+right", "step(10)", "forward 10", show=False),
        Binding("escape", "exit_inspect", "exit inspect", show=False),
        Binding("x", "exit_inspect", "exit inspect", show=False),
    ]

    DEFAULT_CSS = """
    PriceChartPanel > #chart-legend {
        height: 1;
        padding: 0 1;
    }
    PriceChartPanel > PlotextPlot {
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
        yield PlotextPlot(id="chart-plot")

    def show(self, series: list[tuple[str, list[PricePoint]]], interval_key: str) -> None:
        self._series = [(label, pts) for label, pts in series if pts][:MAX_SERIES]
        self._interval = interval_key
        self._inspect_ts = None
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
        self._inspect_ts = self._lead_times[-1]
        self._redraw()

    def action_exit_inspect(self) -> None:
        self._inspect_ts = None
        self.can_focus = False
        self._redraw()
        if self._return_focus is not None and self._return_focus.is_mounted:
            self._return_focus.focus()
        else:
            self.screen.focus_next()

    def action_step(self, delta: int) -> None:
        times = self._lead_times
        if not times or self._inspect_ts is None:
            return
        idx = bisect.bisect_left(times, self._inspect_ts)
        idx = max(0, min(len(times) - 1, idx + delta))
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
        plot = self.query_one(PlotextPlot)
        plt = plot.plt
        plt.clear_figure()
        plt.theme("pro")

        if not self._series:
            plot.refresh()
            return

        all_ts: list[int] = []
        all_ys: list[float] = []
        for i, (_label, points) in enumerate(self._series):
            xs = [p.t for p in points]
            ys = [p.p * 100 for p in points]
            all_ts.extend(xs)
            all_ys.extend(ys)
            plt.plot(xs, ys, marker="braille", color=PALETTE[i % len(PALETTE)])

        lo_t, hi_t = min(all_ts), max(all_ts)
        if hi_t > lo_t:
            n_ticks = 6
            step = (hi_t - lo_t) / (n_ticks - 1)
            positions = [lo_t + round(i * step) for i in range(n_ticks)]
            time_fmt = _time_format(self._interval, hi_t - lo_t)
            labels = [datetime.fromtimestamp(p).astimezone().strftime(time_fmt) for p in positions]
            plt.xticks(positions, labels)

        # Auto-scale with padding (min 10c span) so moves are visible; clamp to 0-100.
        lo_y, hi_y = min(all_ys), max(all_ys)
        pad = max((hi_y - lo_y) * 0.15, (10 - (hi_y - lo_y)) / 2, 0.5)
        plt.ylim(max(0.0, lo_y - pad), min(100.0, hi_y + pad))

        if self._inspect_ts is not None:
            plt.vertical_line(self._inspect_ts, color=CROSSHAIR_COLOR)
            for i, (_label, points) in enumerate(self._series):
                point = self._value_at(points, self._inspect_ts)
                plt.scatter([point.t], [point.p * 100], marker="dot", color=PALETTE[i])
        else:
            # Mark the latest price of the lead series at the right edge.
            lead_pts = self._series[0][1]
            plt.scatter([lead_pts[-1].t], [lead_pts[-1].p * 100], marker="dot", color=PALETTE[0])

        plot.refresh()
