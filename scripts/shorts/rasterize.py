#!/usr/bin/env python3
"""Rasterize an asciinema cast to video frames with pyte + Pillow.

    rasterize.py <cast> <out.mp4> [--fps 30] [--font-size 24]

Prints "WxH" (the frame size) on stdout.

This replaces agg. agg's terminal emulation diverges from a real terminal on
this app's output: panes that leave large regions blank (search results, the
event screen's chart plot) keep ghost text from the previous screen in agg's
output, while tmux and pyte replaying the identical byte stream both show the
regions correctly cleared. pyte gives a faithful grid; Pillow draws it with
the same fonts the caption plates use.

The cast's timestamps are taken as video time (render.py retimes before
calling this). Frames are sampled at a fixed fps; a frame with no terminal
output since the previous one reuses the previous pixels, so cost scales with
how much the screen actually changes. Raw RGB frames are piped straight to
ffmpeg - no intermediate PNGs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont

BG = (10, 14, 22)  # theme.py background - also the canvas colour downstream
FG = (201, 212, 227)
LINE_HEIGHT = 1.4

# Fallback palette for the rare cells that use named ANSI colors rather than
# the app's own truecolor styles.
ANSI = {
    "black": (13, 19, 32), "red": (248, 113, 122), "green": (63, 207, 142),
    "brown": (224, 175, 104), "yellow": (224, 175, 104), "blue": (91, 142, 247),
    "magenta": (187, 154, 247), "cyan": (125, 207, 255), "white": (201, 212, 227),
    "brightblack": (84, 92, 110), "brightred": (248, 113, 122),
    "brightgreen": (63, 207, 142), "brightbrown": (224, 175, 104),
    "brightyellow": (224, 175, 104), "brightblue": (122, 162, 247),
    "brightmagenta": (187, 154, 247), "brightcyan": (125, 207, 255),
    "brightwhite": (233, 238, 244),
}

# macOS keeps user fonts in ~/Library/Fonts; the Linux CI runner installs the
# same Nerd Font files into ~/.local/share/fonts.
FONT_DIR = next(
    (d for d in (Path.home() / "Library/Fonts", Path.home() / ".local/share/fonts")
     if (d / "JetBrainsMonoNerdFont-Regular.ttf").exists()),
    Path.home() / "Library/Fonts",
)


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / name
    if not path.exists():
        raise SystemExit(f"font not found: {path}")
    return ImageFont.truetype(str(path), size)


def colour(value, default):
    if value == "default":
        return default
    if isinstance(value, str):
        if value in ANSI:
            return ANSI[value]
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return default
    return default


class Renderer:
    def __init__(self, cols: int, rows: int, font_size: int):
        self.cols, self.rows = cols, rows
        self.regular = load_font("JetBrainsMonoNerdFont-Regular.ttf", font_size)
        self.bold = load_font("JetBrainsMonoNerdFont-Bold.ttf", font_size)
        self.cw = round(self.regular.getlength("M"))
        self.ch = round(font_size * LINE_HEIGHT)
        # x264 needs even dimensions.
        self.width = (cols * self.cw + 1) // 2 * 2
        self.height = (rows * self.ch + 1) // 2 * 2
        # Baseline offset centres glyphs in the cell.
        ascent, descent = self.regular.getmetrics()
        self.y_off = (self.ch - ascent - descent) // 2

    def frame(self, screen: pyte.Screen) -> bytes:
        img = Image.new("RGB", (self.width, self.height), BG)
        draw = ImageDraw.Draw(img)
        for row in range(self.rows):
            line = screen.buffer[row]
            y = row * self.ch
            # Backgrounds first, merged into runs so wide fills are one rect.
            run_start, run_bg = 0, None
            for col in range(self.cols + 1):
                cell_bg = None
                if col < self.cols:
                    ch = line[col]
                    cell_bg = colour(ch.bg, BG)
                    if ch.reverse:
                        cell_bg = colour(ch.fg, FG)
                    if cell_bg == BG:
                        cell_bg = None
                if cell_bg != run_bg:
                    if run_bg is not None:
                        draw.rectangle(
                            [run_start * self.cw, y, col * self.cw, y + self.ch],
                            fill=run_bg)
                    run_start, run_bg = col, cell_bg
            # Text, batched into same-style runs.
            col = 0
            while col < self.cols:
                ch = line[col]
                if ch.data in ("", " ") or ch.data == "\x00":
                    col += 1
                    continue
                style = (ch.fg, ch.bold, ch.reverse, ch.underscore)
                start = col
                text = []
                while col < self.cols:
                    cur = line[col]
                    if (cur.fg, cur.bold, cur.reverse, cur.underscore) != style:
                        break
                    text.append(cur.data if cur.data else " ")
                    col += 1
                fg = colour(ch.fg, FG)
                if ch.reverse:
                    fg = colour(ch.bg, BG)
                font = self.bold if ch.bold else self.regular
                x = start * self.cw
                run = "".join(text)
                # Draw per-cell x positions via one text call: monospace fonts
                # advance exactly cw per glyph, so a single run stays aligned.
                draw.text((x, y + self.y_off), run, font=font, fill=fg)
                if ch.underscore:
                    uy = y + self.ch - 3
                    draw.line([x, uy, x + len(run) * self.cw, uy], fill=fg)
        return img.tobytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cast", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--font-size", type=int, default=24)
    args = ap.parse_args()

    with open(args.cast) as fh:
        header = json.loads(fh.readline())
        events = [json.loads(line) for line in fh if line.strip()]
    cols = header.get("width", 120)
    rows = header.get("height", 38)

    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    renderer = Renderer(cols, rows, args.font_size)

    duration = events[-1][0] if events else 0.0
    total = int(duration * args.fps) + 1

    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{renderer.width}x{renderer.height}", "-r", str(args.fps),
         "-i", "-",
         "-c:v", "libx264", "-preset", "fast", "-crf", "15",
         "-pix_fmt", "yuv420p", str(args.out)],
        stdin=subprocess.PIPE,
    )
    assert ff.stdin is not None

    idx = 0
    pixels = renderer.frame(screen)
    for n in range(total):
        t = n / args.fps
        changed = False
        while idx < len(events) and events[idx][0] <= t:
            if events[idx][1] == "o":
                stream.feed(events[idx][2])
                changed = True
            idx += 1
        if changed:
            pixels = renderer.frame(screen)
        ff.stdin.write(pixels)
    ff.stdin.close()
    if ff.wait() != 0:
        return 1
    print(f"{renderer.width}x{renderer.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
