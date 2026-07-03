"""Shared plotext chart drawing for one or more price-history series."""

from __future__ import annotations

from datetime import datetime

from textual_plotext import PlotextPlot

from polymarket_tui.models.market import PricePoint

MAX_SERIES = 6


def draw_price_chart(
    plot: PlotextPlot,
    series: list[tuple[str, list[PricePoint]]],
    interval_key: str,
    ylabel: str = "cents",
) -> None:
    """Render series (label, points) onto the plot. Timestamps are the shared x-axis."""
    plt = plot.plt
    plt.clear_figure()
    plt.theme("pro")

    series = [(label, pts) for label, pts in series if pts][:MAX_SERIES]
    if not series:
        plt.title("no price history")
        plot.refresh()
        return

    all_ts: list[int] = []
    all_ys: list[float] = []
    for label, points in series:
        xs = [p.t for p in points]
        ys = [p.p * 100 for p in points]
        all_ts.extend(xs)
        all_ys.extend(ys)
        plt.plot(xs, ys, marker="braille", label=label[:20] if len(series) > 1 else None)

    lo_t, hi_t = min(all_ts), max(all_ts)
    n_ticks = 6
    if hi_t > lo_t:
        step = (hi_t - lo_t) / (n_ticks - 1)
        positions = [lo_t + round(i * step) for i in range(n_ticks)]
        time_fmt = "%H:%M" if interval_key in ("1H", "6H", "1D") else "%b %d"
        labels = [datetime.fromtimestamp(p).astimezone().strftime(time_fmt) for p in positions]
        plt.xticks(positions, labels)

    # Auto-scale with padding (min 10c span) so moves are visible; clamp to 0-100.
    lo_y, hi_y = min(all_ys), max(all_ys)
    pad = max((hi_y - lo_y) * 0.15, (10 - (hi_y - lo_y)) / 2, 0.5)
    plt.ylim(max(0.0, lo_y - pad), min(100.0, hi_y + pad))
    plt.ylabel(ylabel)
    plot.refresh()
