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

Beat-sheet flags:
  clamp_lag  (default true)  cut idle gaps down to MAX_GAP
  timer      (default false) burn in an elapsed-seconds counter
  trim_boot  (default true)  start at the settled home screen, not at launch
"""

from __future__ import annotations

import bisect
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
MAX_GAP = 0.85  # longest idle stretch kept when clamp_lag is on
TIMER_FPS = 10

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
TIMER_SIZE, TIMER_H = 52, 70

# First frame that draws market rows (a volume cell) - a floor for the trim,
# never the anchor: it lands mid-boot, before the category tabs paint.
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


def retime(src: Path, dst: Path, start: float, max_gap: float | None):
    """Rewrite the cast from `start`, optionally clamping idle gaps.

    Returns (duration, to_video) where to_video maps a time on the original
    cast clock to its time in the rendered video. Captions are placed through
    that map, so cutting lag can never slide a caption off the frame it
    describes.

    Events before `start` are kept at zero duration rather than dropped: a cast
    is a stream of incremental terminal writes, so the boot events ARE the
    paint. Delete them and the video opens on an empty terminal that only fills
    in as later writes arrive.
    """
    with open(src) as fh:
        header = json.loads(fh.readline())
        events = [json.loads(line) for line in fh if line.strip()]
    if not events:
        raise SystemExit("no events in cast")

    out: list[list] = []
    marks: list[tuple[float, float]] = []
    shift = 0.0
    prev: float | None = None
    for stamp, kind, data in events:
        if stamp < start:
            out.append([0.0, kind, data])
            continue
        if prev is not None and max_gap and (stamp - prev) > max_gap:
            shift += (stamp - prev) - max_gap
        prev = stamp
        video_t = round(stamp - start - shift, 6)
        out.append([video_t, kind, data])
        marks.append((stamp, video_t))

    with open(dst, "w") as fh:
        fh.write(json.dumps(header) + "\n")
        for event in out:
            fh.write(json.dumps(event) + "\n")

    cast_marks = [m[0] for m in marks]

    def to_video(cast_t: float) -> float:
        i = bisect.bisect_right(cast_marks, cast_t) - 1
        if i < 0:
            return 0.0
        cast_at, video_at = marks[i]
        nxt = marks[i + 1][1] if i + 1 < len(marks) else video_at + (cast_t - cast_at)
        # Inside a clamped gap the offset would overshoot; stop at the next
        # real frame so a caption never lands past the action it labels.
        return min(video_at + (cast_t - cast_at), nxt)

    return (out[-1][0] if out else 0.0), to_video


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
    if len(lines) > limit:
        lines = lines[: limit - 1] + [lines[limit - 1].rstrip(".,") + "..."]
    return lines


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
    for i, line in enumerate(lines):
        draw.text(((W - head_font.getlength(line)) / 2, top + i * HEAD_LH),
                  line, font=head_font, fill=FG)
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
    for i, line in enumerate(wrap(text, fnt, W - 2 * MARGIN)):
        # Lead line in accent blue, continuations in body grey, so a wrapped
        # caption still reads as one unit at a glance.
        colour = BLUE if i == 0 else FG
        draw.text(((W - fnt.getlength(line)) / 2, i * CAP_LH), line, font=fnt, fill=colour)
    path = tmp / f"cap{idx}.png"
    img.save(path)
    return path


def build_timer(duration: float, offset: float, tmp: Path) -> Path:
    """A PNG per tick of an elapsed-seconds counter.

    `offset` is how much real time already ran before video t=0, so the counter
    states true elapsed time since the app launched rather than time since the
    cut. Rendered as a numbered sequence and fed to ffmpeg as one input - a
    per-frame overlay filter would be hundreds of filters in the graph.
    """
    seq = tmp / "timer"
    seq.mkdir()
    fnt = bold(TIMER_SIZE)
    for i in range(int(duration * TIMER_FPS) + 2):
        img = Image.new("RGBA", (W, TIMER_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        label = f"{offset + i / TIMER_FPS:.1f}s"
        draw.text((W - MARGIN - fnt.getlength(label), 0), label, font=fnt, fill=BLUE)
        img.save(seq / f"{i:05d}.png")
    return seq


def main() -> int:
    beats_path, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    spec = json.loads(beats_path.read_text())
    slug = spec["slug"]
    cast = outdir / f"{slug}.cast"
    recorded = json.loads((outdir / f"{slug}.timings.json").read_text())
    timings, head_offset = recorded["beats"], recorded["head_offset"]
    out = outdir / f"{slug}.mp4"

    timer_on = spec.get("timer", False)
    trim_boot = spec.get("trim_boot", True)
    # A clamped video no longer runs at wall-clock speed, so a counter over it
    # would either lie about elapsed time or jump wherever lag was cut. When
    # the short is about speed, keep the real timeline and show the real boot.
    clamp = spec.get("clamp_lag", True) and not timer_on

    for tool in ("agg", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        trimmed = tmp / "trimmed.cast"

        with open(cast) as fh:
            fh.readline()
            events = [json.loads(line) for line in fh if line.strip()]
        first_price = next((e[0] for e in events if CONTENT.search(e[2])), 0.0)
        start = max(first_price, head_offset) if trim_boot else 0.0

        span, to_video = retime(cast, trimmed, start, MAX_GAP if clamp else None)
        duration = span + 1.4  # a beat to read the last caption
        print(f"retime: start={start:.2f}s clamp={clamp} -> {duration:.1f}s")

        gif = tmp / "term.gif"
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
        if not trim_boot and spec.get("boot_caption"):
            # Beats only start once the app is ready, so with the boot left in
            # the opening seconds would otherwise carry no caption at all.
            shown = [{"at": -head_offset, "until": 0.0,
                      "caption": spec["boot_caption"]}] + shown
        caps = [build_caption(b["caption"], i, tmp) for i, b in enumerate(shown)]

        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(plate),
                  "-ignore_loop", "1", "-i", str(gif)]
        for cap in caps:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(cap)]

        steps = [f"[1:v]scale={W}:{term_h}:flags=lanczos[term]",
                 f"[0:v][term]overlay=0:{term_y}[v0]"]
        for i, beat in enumerate(shown):
            # Beat times are on the recorder's clock; map them through the same
            # retime that produced the footage.
            at = to_video(head_offset + beat["at"])
            end = duration if i == len(shown) - 1 else to_video(head_offset + beat["until"])
            steps.append(
                f"[v{i}][{i + 2}:v]overlay=0:{cap_y}:"
                f"enable='between(t,{at:.2f},{end:.2f})'[v{i + 1}]"
            )
        last = f"v{len(shown)}"

        if timer_on:
            seq = build_timer(duration, start, tmp)
            inputs += ["-framerate", str(TIMER_FPS), "-i", str(seq / "%05d.png")]
            steps.append(f"[{last}][{len(caps) + 2}:v]overlay=0:{BRAND_Y - 8}[vt]")
            last = "vt"

        cmd = ["ffmpeg", "-y", *inputs,
               "-filter_complex", ";".join(steps), "-map", f"[{last}]",
               "-t", f"{duration:.2f}",
               "-c:v", "libx264", "-preset", "slow", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
               str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode:
            # Filter-graph errors land in the last stderr lines; the full log is
            # thousands of lines of stream metadata.
            raise SystemExit("ffmpeg failed:\n" + "\n".join(proc.stderr.splitlines()[-12:]))

    print(f"Done: {out} ({duration:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
