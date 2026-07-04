"""Drive the real TUI through a scripted journey, screenshotting each step.

A journey is a JSON file: {"size": [200, 50], "steps": [[name, keys, wait], ...]}
- name: label for the screenshot file
- keys: tmux send-keys arguments (list), e.g. ["Down", "Down", "Enter"]
- wait: seconds to sleep after sending before the snap

Usage:
    uv run python scripts/tui_journey.py journeys/browse.json -o /tmp/shots
Each run boots a fresh app instance in an isolated tmux server.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from tui_snap import ansi_to_png, capture_pane

SOCKET = "pmtui-journey"


def tmux(*args: str) -> None:
    subprocess.check_call(["tmux", "-L", SOCKET, *args])


def run_journey(journey: dict, out_dir: Path, zoom: float) -> list[Path]:
    width, height = journey.get("size", [200, 50])
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.call(
        ["tmux", "-L", SOCKET, "kill-server"],
        stderr=subprocess.DEVNULL,
    )
    tmux(
        "new-session", "-d", "-x", str(width), "-y", str(height),
        journey.get("command", "uv run polymarket-tui; sleep 300"),
    )
    shots: list[Path] = []
    try:
        time.sleep(journey.get("boot_wait", 12))
        for i, (name, keys, wait) in enumerate(journey["steps"]):
            if keys:
                for key in keys:
                    tmux("send-keys", key)
                    time.sleep(0.35)
            time.sleep(wait)
            ansi, w, _h = capture_pane(SOCKET, None)
            png = out_dir / f"{i:02d}_{name}.png"
            ansi_to_png(ansi, w, png, zoom)
            shots.append(png)
            print(png)
    finally:
        subprocess.call(
            ["tmux", "-L", SOCKET, "kill-server"],
            stderr=subprocess.DEVNULL,
        )
    return shots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("journey", help="path to journey JSON")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--zoom", type=float, default=1.5)
    ap.add_argument("--size", default=None, help="WxH override, e.g. 120x35")
    args = ap.parse_args()

    journey = json.loads(Path(args.journey).read_text())
    if args.size:
        w, h = args.size.split("x")
        journey["size"] = [int(w), int(h)]
    run_journey(journey, Path(args.out), args.zoom)


if __name__ == "__main__":
    main()
