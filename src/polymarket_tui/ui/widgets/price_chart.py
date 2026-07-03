"""Price chart panel: legend line with live prices + plotext chart.

The legend is rendered outside the plot (a Rich line above it) so the plot area
stays clean; series colors are deterministic so legend and lines always match.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.containers import Vertical
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


def _rich_color(rgb: tuple[int, int, int]) -> str:
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def _time_format(interval_key: str, span_seconds: float) -> str:
    if interval_key in ("1H", "6H"):
        return "%H:%M"
    if interval_key == "1D":
        # A 1D window usually crosses midnight; disambiguate with the weekday.
        return "%a %H:%M" if span_seconds > 6 * 3600 else "%H:%M"
    return "%b %d"


class PriceChartPanel(Vertical):
    """Legend + chart. Call show(series, interval_key) with (label, points) tuples."""

    DEFAULT_CSS = """
    PriceChartPanel > #chart-legend {
        height: 1;
        padding: 0 1;
    }
    PriceChartPanel > PlotextPlot {
        height: 1fr;
    }
    """

    def compose(self):
        yield Static(id="chart-legend")
        yield PlotextPlot(id="chart-plot")

    def show(self, series: list[tuple[str, list[PricePoint]]], interval_key: str) -> None:
        series = [(label, pts) for label, pts in series if pts][:MAX_SERIES]
        self._draw_legend(series)
        self._draw_plot(series, interval_key)

    # -- legend -----------------------------------------------------------------

    def _draw_legend(self, series: list[tuple[str, list[PricePoint]]]) -> None:
        legend = self.query_one("#chart-legend", Static)
        if not series:
            legend.update(Text("no price history", style="dim"))
            return
        out = Text()
        for i, (label, points) in enumerate(series):
            color = _rich_color(PALETTE[i % len(PALETTE)])
            if i:
                out.append("   ")
            out.append("● ", style=color)
            out.append(label[:22], style=color)
            out.append(f" {fmt.cents(points[-1].p)}", style=f"bold {color}")
        legend.update(out)

    # -- plot -------------------------------------------------------------------

    def _draw_plot(self, series: list[tuple[str, list[PricePoint]]], interval_key: str) -> None:
        plot = self.query_one(PlotextPlot)
        plt = plot.plt
        plt.clear_figure()
        plt.theme("pro")

        if not series:
            plot.refresh()
            return

        all_ts: list[int] = []
        all_ys: list[float] = []
        for i, (_label, points) in enumerate(series):
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
            time_fmt = _time_format(interval_key, hi_t - lo_t)
            labels = [datetime.fromtimestamp(p).astimezone().strftime(time_fmt) for p in positions]
            plt.xticks(positions, labels)

        # Auto-scale with padding (min 10c span) so moves are visible; clamp to 0-100.
        lo_y, hi_y = min(all_ys), max(all_ys)
        pad = max((hi_y - lo_y) * 0.15, (10 - (hi_y - lo_y)) / 2, 0.5)
        y_lo, y_hi = max(0.0, lo_y - pad), min(100.0, hi_y + pad)
        plt.ylim(y_lo, y_hi)

        # Mark the latest price of the lead series at the right edge.
        lead_pts = series[0][1]
        last_t, last_y = lead_pts[-1].t, lead_pts[-1].p * 100
        plt.scatter([last_t], [last_y], marker="dot", color=PALETTE[0])

        plot.refresh()
