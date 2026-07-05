"""Screenshot a running tmux pane as a PNG.

Captures the pane's ANSI content, renders it to SVG via rich, then
rasterizes with resvg. Lets an agent (or human) review the real TUI
visually instead of scraping plain text.

Usage:
    uv run python scripts/tui_snap.py -L pmtui -o /tmp/shot.png
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import TerminalTheme
from rich.text import Text

# Default fg/bg and ANSI palette for the export, matching ui/theme.py -
# otherwise cells the capture leaves unstyled render on rich's default
# background and read as per-line highlight boxes.
PMTUI_TERMINAL_THEME = TerminalTheme(
    (13, 19, 32),
    (201, 212, 227),
    [
        (10, 14, 22),
        (248, 113, 122),
        (63, 207, 142),
        (224, 175, 104),
        (91, 142, 247),
        (187, 154, 247),
        (122, 162, 247),
        (201, 212, 227),
    ],
    [
        (86, 95, 137),
        (248, 113, 122),
        (63, 207, 142),
        (224, 175, 104),
        (91, 142, 247),
        (187, 154, 247),
        (122, 162, 247),
        (255, 255, 255),
    ],
)


def capture_pane(socket: str, target: str | None) -> tuple[str, int, int]:
    base = ["tmux", "-L", socket]
    tcell = ["-t", target] if target else []
    ansi = subprocess.check_output(
        [*base, "capture-pane", "-ep", *tcell], text=True
    )
    dims = subprocess.check_output(
        [*base, "display-message", "-p", *tcell, "#{pane_width} #{pane_height}"],
        text=True,
    )
    width, height = (int(x) for x in dims.split())
    return ansi, width, height


def ansi_to_png(ansi: str, width: int, out_path: Path, zoom: float) -> None:
    console = Console(record=True, width=width, file=open("/dev/null", "w"))
    console.print(Text.from_ansi(ansi), overflow="ignore", crop=False)
    svg = console.export_svg(title="", theme=PMTUI_TERMINAL_THEME)
    with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
        f.write(svg)
        svg_path = f.name
    subprocess.check_call(
        ["resvg", "--zoom", str(zoom), svg_path, str(out_path)]
    )
    Path(svg_path).unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-L", "--socket", default="pmtui")
    ap.add_argument("-t", "--target", default=None, help="tmux target pane")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--zoom", type=float, default=1.0)
    args = ap.parse_args()

    ansi, width, _height = capture_pane(args.socket, args.target)
    ansi_to_png(ansi, width, Path(args.out), args.zoom)
    print(args.out)


if __name__ == "__main__":
    main()
