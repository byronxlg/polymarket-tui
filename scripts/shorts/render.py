#!/usr/bin/env python3
"""Composite a recorded cast into a 1080x1920 short (or a 1920x1080 landscape cut).

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
  pan        (default false) crop the terminal near native resolution and pan
                             between per-beat focus points ("focus": left|mid|
                             right on each beat) instead of scaling the whole
                             frame down. Scaling 120 columns to canvas width
                             leaves ~9px glyphs - unreadable on the phones all
                             of this is watched on; the crop keeps glyphs ~50%
                             larger and the pan adds motion between beats.
  canvas     (default "vertical") "landscape" renders 1920x1080 for the landing
                             page. A 120x38 terminal is ~1.3:1, so it cannot be
                             both wider than a 16:9 canvas and fully visible
                             between the bands: landscape pan mode is a camera
                             instead. Each beat names a 2-D focus ("focus":
                             "top left", "bottom", or anchors [1, 0.18]) and a "zoom"
                             (1.0 = the terminal's full width fills the frame,
                             showing the top ~20 rows; 1.4 shows ~14 rows at
                             ~38px glyphs), and the camera eases between those
                             windows at each beat boundary. The vertical path
                             is untouched by this flag.
  zoom       (default 1.0)   landscape pan only: the zoom a beat gets when it
                             does not set its own
  crf        (default 20)    x264 quality of the final file; the landing page
                             wants ~2-4 MB, so its sheet uses 27
"""

from __future__ import annotations

import bisect
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FPS = 30
MAX_GAP = 0.85  # longest idle stretch kept when clamp_lag is on
TIMER_FPS = 10

BG = (10, 14, 22)  # theme.py background #0a0e16
FG = (201, 212, 227)  # theme.py foreground
BLUE = (91, 142, 247)
MUTED = (122, 134, 156)


@dataclass(frozen=True)
class Layout:
    """Canvas size and the band typography that goes with it."""

    w: int
    h: int
    margin: int
    brand_y: int
    brand_size: int
    head_size: int
    head_lh: int
    cap_size: int
    cap_lh: int
    cap_h: int
    tag_size: int
    tag_y: int
    timer_size: int = 52
    timer_h: int = 70


# A 120x38 terminal is ~1.35:1 inside a 0.5625:1 canvas, so roughly 900px of
# the frame is always band rather than footage. These constants spread that
# slack evenly instead of pooling it at the top and bottom, which reads as an
# unfinished template.
VERTICAL = Layout(w=1080, h=1920, margin=64, brand_y=196, brand_size=36,
                  head_size=54, head_lh=68, cap_size=44, cap_lh=58, cap_h=200,
                  tag_size=36, tag_y=1660)
# Landscape is the opposite problem: the bands are shallow (140px above the
# terminal, 190px below), so the brand mark, headline, caption and tag are each
# one compact line.
LANDSCAPE = Layout(w=1920, h=1080, margin=96, brand_y=16, brand_size=26,
                   head_size=44, head_lh=54, cap_size=36, cap_lh=46, cap_h=100,
                   tag_size=24, tag_y=1026)
LAND_TERM_Y, LAND_TERM_H = 140, 750  # the camera's viewport on the landscape canvas
LAND_FONT_SIZE = 32  # rasterize larger than the vertical default so zooms downscale

PAN_SCALE = 0.95  # terminal display scale in pan mode (1.0 = native pixels)
PAN_RAMP = 0.6  # seconds an eased pan between focus points takes
PAN_MIN_BAND = 300  # px reserved above and below the terminal in pan mode

# First frame that draws market rows (a volume cell) - a floor for the trim,
# never the anchor: it lands mid-boot, before the category tabs paint.
CONTENT = re.compile(r"\$\d")

# macOS keeps user fonts in ~/Library/Fonts; the Linux CI runner installs the
# same Nerd Font files into ~/.local/share/fonts.
FONT_DIR = next(
    (d for d in (Path.home() / "Library/Fonts", Path.home() / ".local/share/fonts")
     if (d / "JetBrainsMonoNerdFont-Regular.ttf").exists()),
    Path.home() / "Library/Fonts",
)


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


def build_plate(spec: dict, lay: Layout, term_y: int, term_h: int, tmp: Path) -> Path:
    """The static background: brand mark, market question, install line."""
    W, H = lay.w, lay.h
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    head_font = bold(lay.head_size)
    lines = wrap(spec["headline"], head_font, W - 2 * lay.margin)
    if lay is LANDSCAPE:
        # Shallow band: brand on its own line at the top, the headline sits on
        # the accent rule just above the terminal. One headline line fits
        # ~55 characters at this size; the wrap is only a guard.
        lines = lines[:1]
        brand_y = lay.brand_y
        top = term_y - 32 - lay.head_lh
    else:
        top = term_y - 48 - lay.head_lh * len(lines)
        # In pan mode the top band is shallow; tuck the brand mark just under
        # the band's top edge instead of at the roomy default.
        brand_y = min(lay.brand_y, max(48, top - lay.brand_size - 40))
    brand = regular(lay.brand_size)
    draw.text(((W - brand.getlength("polymarket-tui")) / 2, brand_y),
              "polymarket-tui", font=brand, fill=BLUE)

    for i, line in enumerate(lines):
        draw.text(((W - head_font.getlength(line)) / 2, top + i * lay.head_lh),
                  line, font=head_font, fill=FG)
    # A short accent rule ties the question to the terminal below it.
    rule_y = term_y - 14 if lay is LANDSCAPE else term_y - 30
    draw.rectangle([(W // 2 - 60, rule_y), (W // 2 + 60, rule_y + 3)], fill=BLUE)

    tag_font = regular(lay.tag_size)
    tag = spec.get("tag", "")
    if tag:
        tag_y = min(lay.tag_y, H - 100)
        tag_y = max(tag_y, term_y + term_h + lay.cap_h + 60)
        if lay is LANDSCAPE:
            tag_y = lay.tag_y
        draw.text(((W - tag_font.getlength(tag)) / 2, tag_y), tag, font=tag_font, fill=MUTED)

    path = tmp / "plate.png"
    img.save(path)
    return path


def pan_x_expr(stops: list[tuple[float, int]]) -> str:
    """A crop-x expression easing between (video_time, x) focus stops.

    Built innermost-first: each earlier stop wraps the expression for
    everything after it, and each stop's blend saturates at its own target so
    the frame holds still between transitions.
    """
    expr = None
    for i in range(len(stops) - 1, -1, -1):
        t0, x = stops[i]
        prev_x = stops[i - 1][1] if i else x
        blend = f"({prev_x}+({x}-{prev_x})*min((t-{t0:.2f})/{PAN_RAMP},1))"
        expr = blend if expr is None else f"if(gte(t,{t0:.2f}),{blend},{expr})"
    return expr or "0"


NAMED_FOCUS = {"left": 0.0, "top": 0.0, "mid": 0.5, "centre": 0.5, "center": 0.5,
               "right": 1.0, "bottom": 1.0}


def parse_focus(value) -> tuple[float, float]:
    """A beat's focus as (x, y) anchors in 0..1 (0 = left/top, 1 = right/bottom).

    Accepts the original one-axis names ("left" / "mid" / "right"), two-axis
    strings for landscape ("top left", "bottom"), or a two-item list where each
    item is a name or a fraction ("focus": [1, 0.18] pins the window's right
    edge to the terminal's and its top 18% of the way down). Unnamed axes
    centre. The vertical path only reads the x anchor.
    """
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise SystemExit(f"focus needs two items, got {value!r}")
        out = []
        for item in value:
            frac = NAMED_FOCUS.get(str(item).lower()) if isinstance(item, str) else float(item)
            if frac is None or not 0.0 <= frac <= 1.0:
                raise SystemExit(f"bad focus anchor {item!r}: a name or 0..1")
            out.append(frac)
        return out[0], out[1]
    fx, fy = 0.5, 0.5
    for token in re.split(r"[\s_-]+", str(value or "mid").strip().lower()):
        if token in ("left", "right"):
            fx = NAMED_FOCUS[token]
        elif token in ("top", "bottom"):
            fy = NAMED_FOCUS[token]
    return fx, fy


def smoothstep(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


Box = tuple[float, float, float, float]  # left, top, right, bottom in source px


def focus_box(fx: float, fy: float, zoom: float, gw: int, gh: int, vw: int, vh: int) -> Box:
    """The source window a beat looks at.

    zoom 1.0 shows the terminal's full width across the viewport; larger zooms
    show proportionally less, anchored to the focus edge. Clamped so the window
    never leaves the terminal - a landscape frame is all footage, never band.
    """
    zoom = max(1.0, zoom)
    w = gw / zoom
    h = w * vh / vw
    if h > gh:  # a very wide viewport: fit the height instead
        h = float(gh)
        w = h * vw / vh
    x, y = fx * (gw - w), fy * (gh - h)
    return (x, y, x + w, y + h)


def camera_box(stops: list[tuple[float, Box]], t: float) -> Box:
    """Where the camera is at video time t: eased from the previous stop over
    PAN_RAMP seconds from each stop's start, held still in between."""
    i = bisect.bisect_right([s[0] for s in stops], t) - 1
    if i < 0:
        return stops[0][1]
    t0, box = stops[i]
    if i == 0:
        return box
    prev = stops[i - 1][1]
    k = smoothstep((t - t0) / PAN_RAMP)
    return tuple(p + (b - p) * k for p, b in zip(prev, box, strict=True))  # type: ignore[return-value]


def run_camera(term: Path, gw: int, gh: int, stops: list[tuple[float, Box]],
               vw: int, vh: int, out: Path) -> None:
    """Re-film the rasterized terminal through a moving window.

    Decodes term.mp4 as raw frames, crops and resamples each through Pillow
    (sub-pixel box, Lanczos) and pipes the result to x264. Done in Python
    rather than ffmpeg's crop/zoompan: crop cannot change its size per frame
    and zoompan resamples bilinearly, which smears terminal glyphs.
    """
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(term), "-f", "rawvideo",
         "-pix_fmt", "rgb24", "pipe:1"],
        stdout=subprocess.PIPE,
    )
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{vw}x{vh}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "fast", "-crf", "15",
         "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE,
    )
    assert dec.stdout is not None and enc.stdin is not None
    size = gw * gh * 3
    n = 0
    prev_raw: bytes | None = None
    prev_box: Box | None = None
    pixels = b""
    while True:
        raw = dec.stdout.read(size)
        if len(raw) < size:
            break
        box = camera_box(stops, n / FPS)
        # Most frames change neither footage nor window; reuse the last crop.
        if raw != prev_raw or box != prev_box:
            frame = Image.frombytes("RGB", (gw, gh), raw)
            pixels = frame.resize((vw, vh), Image.LANCZOS, box=box).tobytes()
            prev_raw, prev_box = raw, box
        enc.stdin.write(pixels)
        n += 1
    enc.stdin.close()
    if dec.wait() != 0 or enc.wait() != 0:
        raise SystemExit("camera pass failed")


def build_caption(text: str, idx: int, lay: Layout, tmp: Path) -> Path:
    W = lay.w
    img = Image.new("RGBA", (W, lay.cap_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = regular(lay.cap_size)
    for i, line in enumerate(wrap(text, fnt, W - 2 * lay.margin)):
        # Lead line in accent blue, continuations in body grey, so a wrapped
        # caption still reads as one unit at a glance.
        colour = BLUE if i == 0 else FG
        draw.text(((W - fnt.getlength(line)) / 2, i * lay.cap_lh), line, font=fnt, fill=colour)
    path = tmp / f"cap{idx}.png"
    img.save(path)
    return path


def build_timer(duration: float, offset: float, lay: Layout, tmp: Path) -> Path:
    """A PNG per tick of an elapsed-seconds counter.

    `offset` is how much real time already ran before video t=0, so the counter
    states true elapsed time since the app launched rather than time since the
    cut. Rendered as a numbered sequence and fed to ffmpeg as one input - a
    per-frame overlay filter would be hundreds of filters in the graph.
    """
    seq = tmp / "timer"
    seq.mkdir()
    fnt = bold(lay.timer_size)
    for i in range(int(duration * TIMER_FPS) + 2):
        img = Image.new("RGBA", (lay.w, lay.timer_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        label = f"{offset + i / TIMER_FPS:.1f}s"
        draw.text((lay.w - lay.margin - fnt.getlength(label), 0), label, font=fnt, fill=BLUE)
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

    canvas = spec.get("canvas", "vertical")
    if canvas not in ("vertical", "landscape"):
        raise SystemExit(f"unknown canvas {canvas!r}: vertical or landscape")
    landscape = canvas == "landscape"
    lay = LANDSCAPE if landscape else VERTICAL
    W, H = lay.w, lay.h

    timer_on = spec.get("timer", False)
    trim_boot = spec.get("trim_boot", True)
    # A clamped video no longer runs at wall-clock speed, so a counter over it
    # would either lie about elapsed time or jump wherever lag was cut. When
    # the short is about speed, keep the real timeline and show the real boot.
    clamp = spec.get("clamp_lag", True) and not timer_on

    for tool in ("ffmpeg", "ffprobe"):
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

        # Rasterize with pyte + Pillow (scripts/shorts/rasterize.py), not agg:
        # agg's emulation leaves ghost text where this app blanks large
        # regions. The rasterizer takes the retimed cast's clock as video time.
        term = tmp / "term.mp4"
        ras_cmd = [sys.executable, str(Path(__file__).with_name("rasterize.py")),
                   str(trimmed), str(term), "--fps", str(FPS)]
        if landscape:
            ras_cmd += ["--font-size", str(LAND_FONT_SIZE)]
        ras = subprocess.run(ras_cmd, capture_output=True, text=True)
        if ras.returncode:
            raise SystemExit("rasterize failed:\n" + ras.stderr[-2000:])
        gw, gh = (int(v) for v in ras.stdout.strip().split("x"))

        pan = spec.get("pan", False)
        camera: list[tuple[float, Box]] = []
        if landscape:
            term_y, term_h = LAND_TERM_Y, LAND_TERM_H
            if pan:
                # focus and zoom live on the sheet's beats; timings align 1:1.
                default_zoom = float(spec.get("zoom", 1.0))
                for beat, sheet_beat in zip(timings, spec["beats"], strict=True):
                    fx, fy = parse_focus(sheet_beat.get("focus"))
                    box = focus_box(fx, fy, float(sheet_beat.get("zoom", default_zoom)),
                                    gw, gh, W, term_h)
                    at = to_video(head_offset + beat["at"])
                    if not camera or camera[-1][1] != box:
                        camera.append((at, box))
                print(f"camera: terminal {gw}x{gh} through {W}x{term_h}, "
                      f"{len(camera)} moves")
            else:
                print(f"terminal {gw}x{gh} fitted to {W}x{term_h} at y={term_y}")
        elif pan:
            # Show a canvas-width window of the near-native terminal. Cap the
            # scale so the bands keep room for the headline and captions.
            scale = min(PAN_SCALE, (H - 2 * PAN_MIN_BAND) / gh)
            sw, sh = round(gw * scale / 2) * 2, round(gh * scale / 2) * 2
            if sw <= W:
                pan = False  # terminal narrower than the window: nothing to pan
        if landscape:
            pass
        elif pan:
            term_h, term_y = sh, (H - sh) // 2
            print(f"pan: terminal {gw}x{gh} scaled {sw}x{sh}, window {W} at y={term_y}")
        else:
            term_h = round(W * gh / gw / 2) * 2
            term_y = (H - term_h) // 2
            print(f"terminal {gw}x{gh} -> {W}x{term_h} at y={term_y}")
        cap_y = term_y + term_h + (24 if landscape else 44)

        plate = build_plate(spec, lay, term_y, term_h, tmp)
        shown = [b for b in timings if b["caption"]]
        if not trim_boot and spec.get("boot_caption"):
            # Beats only start once the app is ready, so with the boot left in
            # the opening seconds would otherwise carry no caption at all.
            shown = [{"at": -head_offset, "until": 0.0,
                      "caption": spec["boot_caption"]}] + shown
        caps = [build_caption(b["caption"], i, lay, tmp) for i, b in enumerate(shown)]

        footage = term
        if landscape and pan:
            footage = tmp / "camera.mp4"
            run_camera(term, gw, gh, camera, W, term_h, footage)

        # The footage stops at the last beat's end and the overlay repeats that
        # frame through the tail that reads the last caption: what the cast holds
        # after the beats is the quit (a `q` typed into a search box, then the app
        # gone), never footage the caption labels.
        footage_end = to_video(head_offset + timings[-1]["until"])
        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(plate),
                  "-t", f"{footage_end:.2f}", "-i", str(footage)]
        for cap in caps:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(cap)]

        if landscape and pan:
            steps = [f"[0:v][1:v]overlay=0:{term_y}[v0]"]
        elif landscape:
            fit_w = round(term_h * gw / gh / 2) * 2
            steps = [f"[1:v]scale={fit_w}:{term_h}:flags=lanczos[term]",
                     f"[0:v][term]overlay={(W - fit_w) // 2}:{term_y}[v0]"]
        elif pan:
            stops: list[tuple[float, int]] = []
            # focus lives on the sheet's beats; timings align with them 1:1.
            for beat, sheet_beat in zip(timings, spec["beats"], strict=True):
                x = round(parse_focus(sheet_beat.get("focus"))[0] * (sw - W))
                at = to_video(head_offset + beat["at"])
                if not stops or stops[-1][1] != x:
                    stops.append((at, x))
            x_expr = pan_x_expr(stops)
            steps = [f"[1:v]scale={sw}:{sh}:flags=lanczos,"
                     f"crop=w={W}:h={sh}:x='{x_expr}':y=0[term]",
                     f"[0:v][term]overlay=0:{term_y}[v0]"]
        else:
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
            seq = build_timer(duration, start, lay, tmp)
            inputs += ["-framerate", str(TIMER_FPS), "-i", str(seq / "%05d.png")]
            steps.append(f"[{last}][{len(caps) + 2}:v]overlay=0:{lay.brand_y - 8}[vt]")
            last = "vt"

        # Mux a silent AAC track. These shorts have no sound by design, but a
        # file with no audio stream at all is rejected outright by Instagram
        # Reels and trips some TikTok upload paths - platforms assume every
        # video has one.
        audio_idx = len(caps) + 3 if timer_on else len(caps) + 2
        inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

        cmd = ["ffmpeg", "-y", *inputs,
               "-filter_complex", ";".join(steps),
               "-map", f"[{last}]", "-map", f"{audio_idx}:a",
               "-t", f"{duration:.2f}",
               "-c:v", "libx264", "-preset", "slow", "-crf", str(int(spec.get("crf", 20))),
               "-c:a", "aac", "-b:a", "96k", "-ac", "2",
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
