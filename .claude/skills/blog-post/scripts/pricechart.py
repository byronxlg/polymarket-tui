#!/usr/bin/env python3
"""Render a price-history line chart as inline SVG for blog posts.

Stdlib only, so it runs identically on a laptop and in the GitHub Actions
runner. Reads a JSON spec on stdin, writes an SVG fragment to stdout that is
meant to be pasted inline into a post inside <figure class="fig">.

Spec:
{
  "alt": "Spain's championship price rose from 16c to 59c over the week",
  "series": [
    {"name": "Spain", "color": "accent",
     "points": [[epoch_seconds, price_cents], ...]}
  ],
  "annotations": [{"t": epoch_seconds, "label": "Spain 2-0 France"}],
  "ymin": 0, "ymax": 100        # optional; default fits the data
}

Colors are named tokens, not hexes, so every chart matches the site theme.
"accent"/"amber" is the two-series pair validated for colorblind separation
and lightness band against the dark surface (dataviz six-checks validator,
2026-07-17); green/red are reserved for series that ARE a Yes/No outcome.
Text stays in ink/dim/faint tokens per the site rule that text never wears
the series color.
"""

import json
import sys
from datetime import datetime, timezone

COLORS = {
    "accent": "#4d8bf5",
    "amber": "#bd8b2b",  # chart step of the theme amber; in-band on dark bg
    "green": "#41b866",
    "red": "#e05a51",
}
INK = "#c9d3df"
DIM = "#828f9e"
FAINT = "#57626f"
LINE = "#1b232e"
LINE2 = "#29323f"

W, H = 720, 300
ML, MR, MT, MB = 46, 118, 16, 34


def nice_ticks(lo, hi):
    span = max(hi - lo, 1e-9)
    for step in (1, 2, 5, 10, 20, 25, 50):
        if span / step <= 5:
            break
    t0 = int(lo // step) * step
    ticks = [t for t in range(t0, int(hi) + step + 1, step) if lo - 1e-9 <= t <= hi + 1e-9]
    return ticks or [lo, hi]


def fmt_time(ts, span):
    d = datetime.fromtimestamp(ts, tz=timezone.utc)
    if span > 3 * 86400:
        return d.strftime("%b %d")
    if span > 86400:
        return d.strftime("%b %d %H:%M")
    return d.strftime("%H:%M")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
    spec = json.load(sys.stdin)
    series = spec["series"]
    if not series or any(not s["points"] for s in series):
        sys.exit("every series needs at least one point")
    for s in series:
        s["points"] = sorted(s["points"])

    all_p = [p for s in series for _, p in s["points"]]
    all_t = [t for s in series for t, _ in s["points"]]
    t_lo, t_hi = min(all_t), max(all_t)
    span = max(t_hi - t_lo, 1)

    pad = (max(all_p) - min(all_p)) * 0.10 + 1
    y_lo = spec.get("ymin", max(0, min(all_p) - pad))
    y_hi = spec.get("ymax", min(100, max(all_p) + pad))
    yticks = nice_ticks(y_lo, y_hi)
    y_lo, y_hi = min(y_lo, yticks[0]), max(y_hi, yticks[-1])

    anns = spec.get("annotations", [])
    # one label row per annotation up to two rows, staggered so neighbours
    # don't read as one run-on line
    top = MT + (16 if len(series) > 1 else 0) + (14 * min(len(anns), 2))
    pw, ph = W - ML - MR, H - top - MB

    def X(t):
        return ML + (t - t_lo) / span * pw

    def Y(p):
        return top + (y_hi - p) / (y_hi - y_lo) * ph

    out = []
    out.append(
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(spec.get("alt", ""))}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    out.append(f"<title>{esc(spec.get('alt', 'price chart'))}</title>")
    out.append('<g font-size="10.5" font-family="inherit">')

    # horizontal grid + y labels (recessive: hairlines, faint text)
    for yt in yticks:
        y = Y(yt)
        out.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML + pw}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        out.append(f'<text x="{ML - 8}" y="{y + 3.5:.1f}" text-anchor="end" fill="{FAINT}">{yt:g}c</text>')

    # x labels
    for i in range(4):
        t = t_lo + span * i / 3
        anchor = "start" if i == 0 else ("end" if i == 3 else "middle")
        out.append(
            f'<text x="{X(t):.1f}" y="{top + ph + 18}" text-anchor="{anchor}" '
            f'fill="{FAINT}">{fmt_time(t, span)}</text>'
        )

    # annotations: dashed vertical + label at plot top, alternating two rows
    for i, a in enumerate(anns):
        x = X(a["t"])
        ly = top - 4 - (i % 2) * 14
        out.append(
            f'<line x1="{x:.1f}" y1="{ly + 3:.1f}" x2="{x:.1f}" y2="{top + ph}" '
            f'stroke="{LINE2}" stroke-width="1" stroke-dasharray="3 4"/>'
        )
        out.append(f'<text x="{x + 5:.1f}" y="{ly:.1f}" fill="{DIM}" font-size="10">{esc(a["label"])}</text>')

    # legend row (2+ series), swatch + name in dim ink
    if len(series) > 1:
        lx = ML
        for s in series:
            c = COLORS[s.get("color", "accent")]
            out.append(f'<line x1="{lx}" y1="{MT + 4}" x2="{lx + 16}" y2="{MT + 4}" stroke="{c}" stroke-width="2"/>')
            name = esc(s["name"])
            out.append(f'<text x="{lx + 21}" y="{MT + 8}" fill="{DIM}">{name}</text>')
            lx += 21 + 6.6 * len(s["name"]) + 22

    # series lines, area fill for single series, end dot + direct label
    end_ys = []
    for s in series:
        c = COLORS[s.get("color", "accent")]
        pts = " ".join(f"{X(t):.1f},{Y(p):.1f}" for t, p in s["points"])
        if len(series) == 1:
            first_x, last_x = X(s["points"][0][0]), X(s["points"][-1][0])
            base = top + ph
            out.append(f'<polygon points="{first_x:.1f},{base} {pts} {last_x:.1f},{base}" fill="{c}" opacity="0.08"/>')
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        lt, lp = s["points"][-1]
        ly = Y(lp)
        # nudge stacked end labels apart
        while any(abs(ly - e) < 14 for e in end_ys):
            ly += 14
        end_ys.append(ly)
        out.append(f'<circle cx="{X(lt):.1f}" cy="{Y(lp):.1f}" r="3" fill="{c}"/>')
        out.append(
            f'<text x="{X(lt) + 8:.1f}" y="{ly + 4:.1f}" fill="{INK}" font-size="11">'
            f'{esc(s["name"])} {lp:g}c</text>'
        )

    out.append("</g></svg>")
    print("\n".join(out))


if __name__ == "__main__":
    main()
