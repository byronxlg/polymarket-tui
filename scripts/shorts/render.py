#!/usr/bin/env python3
"""Composite a recorded cast into a 1080x1920 short.

    render.py <beats.json> <outdir>

Reads <outdir>/<slug>.cast and <outdir>/<slug>.timings.json (written by
record.sh) and produces <outdir>/<slug>.mp4.

The terminal is never squeezed to phone aspect - the app's own layout breaks
below ~100 columns (see record.sh). Instead the native 120x38 capture is
scaled to the full canvas width and centred, with the market question above it
and beat captions below. That band structure is also what makes the video
readable muted, which is how nearly all of it will be watched.

Text is drawn with Pillow into PNG plates and overlaid, not with ffmpeg's
drawtext: Homebrew's ffmpeg ships without libfreetype, so drawtext does not
exist on this machine. Pillow also measures strings properly, so wrapping is
exact rather than an assumed character advance.

Captions are burned in rather than uploaded as a subtitle track: every target
platform renders its own captions differently (or not at all on a repost), and
a caption describing what the cursor is doing is part of the footage, not an
accessibility layer on top of it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
MARGIN = 64

BG = (10, 14, 22)  # theme.py background #0a0e16
FG = (201, 212, 227)  # theme.py foreground
BLUE = (91, 142, 247)
MUTED = (122, 134, 156)

# A 120x38 terminal is ~1.35:1 inside a 0.5625:1 canvas, so roughly 900px of
# the frame is always band rather than footage. These constants spread that
# slack evenly instead of pooling it at the top and bottom, which reads as an
# unfinished template.
BRAND_Y, BRAND_SIZE = 196, 36
HEAD_SIZE, HEAD_LH = 54, 68
CAP_SIZE, CAP_LH, CAP_H = 44, 58, 200
TAG_SIZE, TAG_Y = 36, 1660

# First frame that draws market rows (a volume cell). Everything before it is
# python boot and an empty shell; the recorder's beat clock starts here too, so
# cutting at this frame is what keeps captions aligned to the frames they
# describe.
CONTENT = re.compile(r"\$\d")

FONT_DIR = Path.home() / "Library/Fonts"


def font(size: int, *names: str) -> ImageFont.FreeTypeFont:
    for name in names:
        path = FONT_DIR / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise SystemExit(f"no font found among {names} in {FONT_DIR}")


def bold(size: int) -> ImageFont.FreeTypeFont:
    return font(size, "JetBrainsMonoNerdFont-Bold.ttf", "JetBrainsMonoNerdFont-ExtraBold.ttf")


def regular(size: int) -> ImageFont.FreeTypeFont:
    return font(size, "JetBrainsMonoNerdFont-Regular.ttf", "JetBrainsMonoNerdFont-Medium.ttf")


def trim_head(src: Path, dst: Path, head_offset: float) -> float:
    """Copy src to dst from the recorder's ready instant on, rebased to t=0.

    head_offset comes from record.sh and is the same origin the beat clock uses,
    which is the only reason captions line up with the frames they describe.
    The first-price frame is a floor, not the anchor: it lands mid-boot, before
    the category tabs paint.

    Returns the trimmed duration. Idle gaps are left alone - the beat waits are
    already tight and scripted, and clamping them would desync the captions.
    """
    with open(src) as fh:
        header = json.loads(fh.readline())
        events = [json.loads(line) for line in fh if line.strip()]
    if not events:
        raise SystemExit("no events in cast")

    first_price = next((e[0] for e in events if CONTENT.search(e[2])), events[0][0])
    start = max(first_price, head_offset)
    # Keep the head events at zero duration rather than dropping them. A cast is
    # a stream of incremental terminal writes, so the boot events ARE the paint:
    # delete them and the video opens on an empty terminal that only fills in as
    # later writes arrive. Zeroing replays the paint instantly instead.
    kept = [[0.0 if e[0] < start else round(e[0] - start, 6), e[1], e[2]] for e in events]
    with open(dst, "w") as fh:
        fh.write(json.dumps(header) + "\n")
        for event in kept:
            fh.write(json.dumps(event) + "\n")
    return kept[-1][0]


def wrap(text: str, fnt: ImageFont.FreeTypeFont, width: int, limit: int = 3) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        candidate = f"{cur} {word}".strip()
        if fnt.getlength(candidate) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    while len(lines) > limit:
        lines = lines[: limit - 1] + [lines[limit - 1].rstrip(".,") + "..."]
        break
    return lines


def centred(draw: ImageDraw.ImageDraw, lines: list[str], fnt, colour, top: int, lh: int) -> None:
    for i, line in enumerate(lines):
        draw.text(((W - fnt.getlength(line)) / 2, top + i * lh), line, font=fnt, fill=colour)


def build_plate(spec: dict, term_y: int, tmp: Path) -> Path:
    """The static background: brand mark, market question, install line."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    brand = regular(BRAND_SIZE)
    draw.text(((W - brand.getlength("polymarket-tui")) / 2, BRAND_Y),
              "polymarket-tui", font=brand, fill=BLUE)

    head_font = bold(HEAD_SIZE)
    lines = wrap(spec["headline"], head_font, W - 2 * MARGIN)
    top = term_y - 56 - HEAD_LH * len(lines)
    centred(draw, lines, head_font, FG, top, HEAD_LH)
    # A short accent rule ties the question to the terminal below it.
    draw.rectangle([(W // 2 - 60, term_y - 34), (W // 2 + 60, term_y - 31)], fill=BLUE)

    tag_font = regular(TAG_SIZE)
    tag = spec.get("tag", "")
    if tag:
        draw.text(((W - tag_font.getlength(tag)) / 2, TAG_Y), tag, font=tag_font, fill=MUTED)

    path = tmp / "plate.png"
    img.save(path)
    return path


def build_caption(text: str, idx: int, tmp: Path) -> Path:
    img = Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = regular(CAP_SIZE)
    lines = wrap(text, fnt, W - 2 * MARGIN)
    for i, line in enumerate(lines):
        # Lead line in accent blue, continuations in body grey, so a wrapped
        # caption still reads as one unit at a glance.
        colour = BLUE if i == 0 else FG
        draw.text(((W - fnt.getlength(line)) / 2, i * CAP_LH), line, font=fnt, fill=colour)
    path = tmp / f"cap{idx}.png"
    img.save(path)
    return path


def main() -> int:
    beats_path, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    spec = json.loads(beats_path.read_text())
    slug = spec["slug"]
    cast = outdir / f"{slug}.cast"
    recorded = json.loads((outdir / f"{slug}.timings.json").read_text())
    timings = recorded["beats"]
    head_offset = recorded["head_offset"]
    out = outdir / f"{slug}.mp4"

    for tool in ("agg", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        trimmed = tmp / "trimmed.cast"
        # a beat to read the last caption
        duration = trim_head(cast, trimmed, head_offset) + 1.4

        gif = tmp / "term.gif"
        print(f"agg -> {gif} ({duration:.1f}s)")
        subprocess.run(
            ["agg", "--font-size", "24", "--line-height", "1.4", "--fps-cap", str(FPS),
             "--idle-time-limit", "2", "--no-loop", "-q", str(trimmed), str(gif)],
            check=True,
        )

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0", str(gif)],
            check=True, capture_output=True, text=True,
        ).stdout.strip().split(",")
        gw, gh = int(probe[0]), int(probe[1])
        term_h = round(W * gh / gw / 2) * 2
        term_y = (H - term_h) // 2
        cap_y = term_y + term_h + 60
        print(f"terminal {gw}x{gh} -> {W}x{term_h} at y={term_y}")

        plate = build_plate(spec, term_y, tmp)
        shown = [b for b in timings if b["caption"]]
        caps = [build_caption(b["caption"], i, tmp) for i, b in enumerate(shown)]

        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(plate),
                  "-ignore_loop", "1", "-i", str(gif)]
        for cap in caps:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(cap)]

        steps = [f"[1:v]scale={W}:{term_h}:flags=lanczos[term]",
                 f"[0:v][term]overlay=0:{term_y}[v0]"]
        for i, beat in enumerate(shown):
            # Hold the last caption to the end so the video never dead-ends on
            # a bare terminal frame.
            end = duration if i == len(shown) - 1 else beat["until"]
            steps.append(
                f"[v{i}][{i + 2}:v]overlay=0:{cap_y}:"
                f"enable='between(t,{beat['at']:.2f},{end:.2f})'[v{i + 1}]"
            )
        final = f"v{len(shown)}"

        cmd = ["ffmpeg", "-y", *inputs,
               "-filter_complex", ";".join(steps), "-map", f"[{final}]",
               "-t", f"{duration:.2f}",
               "-c:v", "libx264", "-preset", "slow", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
               str(out)]
        print("ffmpeg ...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode:
            # Filter-graph errors land in the last stderr lines; the full log is
            # thousands of lines of stream metadata.
            raise SystemExit("ffmpeg failed:\n" + "\n".join(proc.stderr.splitlines()[-12:]))

    print(f"Done: {out} ({duration:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
