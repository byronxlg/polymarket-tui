"""Price chart panel: legend line with live prices + smooth line chart.

The legend is rendered outside the plot (a Rich line above it) so the plot area
stays clean; series colors are deterministic so legend and lines always match.
The chart is display-only context - it never takes focus.
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

from polymarket_tui.core import fmt
from polymarket_tui.models.market import PricePoint
from polymarket_tui.ui.widgets.linechart import render_chart

MAX_SERIES = 6

# One palette, used for both the chart lines and the Rich legend swatches.
PALETTE: list[tuple[int, int, int]] = [
    (0, 187, 255),  # sky blue
    (255, 155, 66),  # orange
    (46, 204, 113),  # green
    (231, 76, 60),  # red
    (187, 134, 252),  # purple
    (241, 196, 15),  # yellow
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
    return fmt.cents(delta, signed=True), ("green" if delta > 0 else "red")


class PriceChartPanel(Vertical):
    """Legend + chart. Call show(series, interval_key) with (label, points) tuples."""

    DEFAULT_CSS = """
    PriceChartPanel > #chart-legend {
        height: 1;
        padding: 0 1;
    }
    PriceChartPanel > #chart-canvas {
        height: 1fr;
    }
    """

    can_focus = False  # display-only context, never focused

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._series: list[tuple[str, list[PricePoint]]] = []
        self._interval = "1D"

    def compose(self):
        yield Static(id="chart-legend")
        yield Static(id="chart-canvas")

    def on_resize(self) -> None:
        self._draw_plot()

    def show(self, series: list[tuple[str, list[PricePoint]]], interval_key: str) -> None:
        self._series = [(label, pts) for label, pts in series if pts][:MAX_SERIES]
        self._interval = interval_key
        self._redraw()

    def _redraw(self) -> None:
        self._draw_legend()
        self._draw_plot()

    # -- legend -----------------------------------------------------------------

    def _draw_legend(self) -> None:
        legend = self.query_one("#chart-legend", Static)
        if not self._series:
            legend.update(Text("no price history", style="dim"))
            return
        out = Text()
        for i, (label, points) in enumerate(self._series):
            color = _rich_color(PALETTE[i % len(PALETTE)])
            if i:
                out.append("   ")
            out.append("● ", style=color)
            out.append(fmt.trunc(label, 22), style=color)
            out.append(f" {fmt.cents(points[-1].p)}", style=f"bold {color}")
            # Change over the visible window.
            delta = points[-1].p - points[0].p
            text, style = _change_text(delta)
            out.append(f" {text}", style=style)
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
            )
        )
