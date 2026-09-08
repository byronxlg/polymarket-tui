"""Assemble the product-first short: real TUI footage leads, story supports.

    uv run --no-project --with pillow python make_product_short.py \
        --term <term.mp4> --wide <trader-monitors-push.mp4> --vo <vo-dir> \
        --out out/product-first.mp4

Inverse of make_short.py's shape ("start with the product" - Byron,
2026-08-16): the hook and six of nine beats are the real terminal, the AI
clip appears once for the money line, cards close. Same rules otherwise:
per-line mp3s ARE the caption windows, every line changes the visual, all
numbers must be re-verified against the live leaderboard before recording
the voiceover.

--term is the native-resolution rasterized cast (scripts/shorts/rasterize.py,
1680x1258 for 120x38). Segments below are cast-time windows plus a crop
origin: the footage slot is 1080x1080 at native scale, so a crop IS the
zoom, and different origins on the same screen read as different shots.
SEGMENTS must be re-timed when the footage is re-recorded - they follow the
beat timestamps in the recording's timings.json (head_offset + at).
"""

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
WORK = HERE / "work-product"

# ui/theme.py palette - keep in sync
SURFACE = (13, 19, 32)
UP = "#3fcf8e"
BLUE = "#5b8ef7"
MUTED = "#8a93a6"
WHITE = "#e6e9f0"

# (start, crop_x, crop_y) in the term.mp4 clock; crop is 1080x1080.
# Timed for the 2026-08-16 recording (head_offset 4.858).
SEGMENTS = {
    # starts after the websocket connects: the header must read "streaming",
    # not "polling", under a "live order book" claim
    "book": (13.2, 340, 140),
    "search": (7.1, 280, 0),
    "ladder": (44.9, 0, 100),
    "chart": (24.4, 300, 178),
    "cursor": (18.4, 470, 178),  # deeper crop than "book" so it reads as a new shot
    "review": (32.9, 600, 0),
}

# (vo file index, caption, visual) - visual: segment name, "wide", or card id.
LINES = [
    (1, None, "book"),  # hook caption is custom-drawn below
    (2, "Type a headline.\nIt's a market.", "search"),
    (3, "Every date\nhas a price", "ladder"),
    (4, "News breaks.\nChart moves.", "chart"),
    (5, "#1 trader:\n+$23,000,000", "wide"),
    (6, "Every bid.\nLive.", "cursor"),
    (7, "Cost + payout\nbefore you commit", "review"),
    (8, None, "cardFeatures"),  # the card carries its own text - no duplicate caption
    (9, None, "cardCTA"),
]

FONTS = Path.home() / "Library/Fonts"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONTS / name
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size)


def bold(size: int) -> ImageFont.FreeTypeFont:
    return font("JetBrainsMonoNerdFont-Bold.ttf", size)


def reg(size: int) -> ImageFont.FreeTypeFont:
    return font("JetBrainsMonoNerdFont-Regular.ttf", size)


def probe(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True)
    return round(float(out.stdout.strip()), 3)


def center_text(draw, xy_center, text, fnt, fill):
    x, y = xy_center
    bbox = draw.multiline_textbbox((0, 0), text, font=fnt, align="center")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.multiline_text((x - w / 2, y - h / 2), text, font=fnt, fill=fill,
                        align="center", spacing=18)


def build_overlays(overlays: Path) -> None:
    overlays.mkdir(parents=True, exist_ok=True)

    # Hook: the product claim dominates from frame one.
    im = Image.new("RGBA", (1080, 440), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def center_line(y, text, fnt, fill):
        w = d.textlength(text, font=fnt)
        d.text(((1080 - w) / 2, y), text, font=fnt, fill=fill)

    center_line(70, "LIVE ORDER BOOK", bold(92), UP)
    center_line(210, "in your terminal", bold(60), WHITE)
    im.save(overlays / "cap00.png")

    for i, (_, caption, _) in enumerate(LINES):
        if caption is None:
            continue
        im = Image.new("RGBA", (1080, 440), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        center_text(d, (540, 200), caption, bold(60), WHITE)
        im.save(overlays / f"cap{i:02d}.png")

    im = Image.new("RGBA", (1080, 280), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    center_text(d, (540, 150), "POLYMARKET / IN THE TERMINAL", reg(34), MUTED)
    im.save(overlays / "toplabel.png")

    im = Image.new("RGBA", (1080, 1080), (*SURFACE, 255))
    d = ImageDraw.Draw(im)
    center_text(d, (540, 300), "polymarket-tui", bold(96), BLUE)
    center_text(d, (540, 430), "live books / charts / trading", reg(40), MUTED)
    center_text(d, (540, 560), "free + open source", bold(52), WHITE)
    im.save(overlays / "cardFeatures.png")

    im = Image.new("RGBA", (1080, 1080), (*SURFACE, 255))
    d = ImageDraw.Draw(im)
    center_text(d, (540, 300), "polymarket-tui", bold(96), BLUE)
    d.rounded_rectangle([70, 470, 1010, 610], radius=16, outline=MUTED, width=3)
    center_text(d, (540, 540), "$ uv tool install polymarket-tui", bold(44), UP)
    center_text(d, (540, 720), "or: brew install byronxlg/tap/polymarket-tui",
                reg(32), MUTED)
    im.save(overlays / "cardCTA.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", type=Path, required=True)
    ap.add_argument("--wide", type=Path, required=True)
    ap.add_argument("--vo", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "out" / "product-first.mp4")
    args = ap.parse_args()

    overlays = WORK / "overlays"
    durs = [probe(args.vo / f"line{i:02d}.mp3") for i, _, _ in LINES]
    starts = [round(sum(durs[:i]), 3) for i in range(len(durs))]
    ends = [round(s + d, 3) for s, d in zip(starts, durs, strict=True)]
    total = round(sum(durs), 3)

    build_overlays(overlays)

    with open(WORK / "vo_list.txt", "w") as f:
        for i, _, _ in LINES:
            f.write(f"file '{args.vo}/line{i:02d}.mp3'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(WORK / "vo_list.txt"), "-c:a", "aac",
                    "-b:a", "160k", str(WORK / "vo_full.m4a")],
                   check=True, capture_output=True)

    # One input per TUI segment (seeked), one wide clip, overlays, audio.
    inputs = []
    fc = [f"color=c=0x0d1320:s=1080x1920:d={total}[base]"]
    seg_lines = [(n, line) for n, (_, _, vis) in enumerate(LINES)
                 for line in [LINES[n]] if vis in SEGMENTS]
    idx = 0
    stream_of = {}
    for n, (_, _, vis) in enumerate(LINES):
        if vis not in SEGMENTS:
            continue
        t0, cx, cy = SEGMENTS[vis]
        inputs += ["-ss", str(t0), "-i", str(args.term)]
        fc.append(f"[{idx}:v]crop=1080:1080:{cx}:{cy},setsar=1,"
                  f"setpts=PTS-STARTPTS+{starts[n]}/TB[seg{n}]")
        stream_of[n] = f"seg{n}"
        idx += 1
    wide_n = next(n for n, (_, _, vis) in enumerate(LINES) if vis == "wide")
    inputs += ["-stream_loop", "1", "-i", str(args.wide)]
    fc.append(f"[{idx}:v]setpts=PTS-STARTPTS+{starts[wide_n]}/TB,"
              f"scale=1080:1080,setsar=1[seg{wide_n}]")
    stream_of[wide_n] = f"seg{wide_n}"
    idx += 1

    card_input = {}
    for name in ("cardFeatures", "cardCTA", "toplabel"):
        inputs += ["-i", str(overlays / f"{name}.png")]
        card_input[name] = idx
        idx += 1
    cap_input = {}
    for n in range(len(LINES)):
        p = overlays / f"cap{n:02d}.png"
        if p.exists():
            inputs += ["-i", str(p)]
            cap_input[n] = idx
            idx += 1
    inputs += ["-i", str(WORK / "vo_full.m4a")]
    audio_idx = idx

    prev = "base"
    for n, (_, _, vis) in enumerate(LINES):
        if n in stream_of:
            end = ends[n]
            fc.append(f"[{prev}][{stream_of[n]}]overlay=0:280:"
                      f"enable='between(t,{starts[n]},{end})'[v{n}]")
            prev = f"v{n}"
        elif vis.startswith("card"):
            end = total if n == len(LINES) - 1 else ends[n]
            fc.append(f"[{prev}][{card_input[vis]}:v]overlay=0:280:"
                      f"enable='between(t,{starts[n]},{end})'[v{n}]")
            prev = f"v{n}"
    for n, i in cap_input.items():
        fc.append(f"[{prev}][{i}:v]overlay=0:1440:"
                  f"enable='between(t,{starts[n]},{ends[n]})'[c{n}]")
        prev = f"c{n}"
    fc.append(f"[{prev}][{card_input['toplabel']}:v]overlay=0:0[vout]")

    args.out.parent.mkdir(exist_ok=True)
    proc = subprocess.run(["ffmpeg", "-y", *inputs,
                           "-filter_complex", ";".join(fc),
                           "-map", "[vout]", "-map", f"{audio_idx}:a",
                           "-t", str(total), "-r", "24",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                           "-movflags", "+faststart", str(args.out)],
                          capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit("ffmpeg failed:\n" + "\n".join(proc.stderr.splitlines()[-12:]))
    print(f"wrote {args.out} ({total}s)")


if __name__ == "__main__":
    main()
