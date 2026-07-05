#!/usr/bin/env python3
"""Trim an asciinema v2 cast: drop the leading load gap and clamp long idle
gaps so the demo plays tight. Reads RAW, writes OUT.

Usage: trim_cast.py in.cast out.cast [max_gap_seconds]
"""

from __future__ import annotations

import json
import re
import sys

MAX_GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 1.4
LEAD_SKIP = 0.5  # collapse the initial silence before the first paint to this
# First frame that draws market rows (a volume cell). Everything before it -
# python boot, the empty shell, the ticking clock while data loads - plays at
# zero duration: gap-clamping alone cannot cut the head because the ms clock
# repaints continuously, so there are no gaps to clamp.
CONTENT = re.compile(r"\$\d")


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as fh:
        header = json.loads(fh.readline())
        events = [json.loads(line) for line in fh if line.strip()]

    if not events:
        raise SystemExit("no events in cast")

    content_at = next(
        (i for i, (_, kind, data) in enumerate(events) if kind == "o" and CONTENT.search(data)),
        0,
    )

    # Rebuild timestamps: play the pre-content head instantly, give the
    # first content frame a short beat, clamp every later gap.
    out = []
    prev_src = events[0][0]
    t = 0.0
    for i, (ts, kind, data) in enumerate(events):
        gap = ts - prev_src
        prev_src = ts
        if i < content_at:
            gap = 0.0
        elif i == content_at:
            gap = LEAD_SKIP
        else:
            gap = min(max(gap, 0.0), MAX_GAP)
        t += gap
        out.append([round(t, 3), kind, data])

    with open(dst, "w") as fh:
        fh.write(json.dumps(header) + "\n")
        for ev in out:
            fh.write(json.dumps(ev) + "\n")

    print(f"{len(out)} events, {out[-1][0]:.1f}s (was {events[-1][0]:.1f}s)")


if __name__ == "__main__":
    main()
