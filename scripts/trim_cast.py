#!/usr/bin/env python3
"""Trim an asciinema v2 cast: drop the leading load gap and clamp long idle
gaps so the demo plays tight. Reads RAW, writes OUT.

Usage: trim_cast.py in.cast out.cast [max_gap_seconds]
"""

from __future__ import annotations

import json
import sys

MAX_GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 1.4
LEAD_SKIP = 0.5  # collapse the initial silence before the first paint to this


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as fh:
        header = json.loads(fh.readline())
        events = [json.loads(line) for line in fh if line.strip()]

    if not events:
        raise SystemExit("no events in cast")

    # Rebuild timestamps: skip leading idle, clamp inter-event gaps.
    out = []
    prev_src = events[0][0]
    t = 0.0
    first = True
    for ts, kind, data in events:
        gap = ts - prev_src
        prev_src = ts
        if first:
            gap = min(gap, LEAD_SKIP)
            first = False
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
