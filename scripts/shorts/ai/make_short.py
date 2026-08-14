"""Assemble "The $23M Trader" AI-clip short (1080x1920).

Manual pipeline - no automation. See README.md in this directory for the
full workflow (story data, script rules, voiceover, clip generation).

Inputs (all relative to this file):
  clips/night-terminal-push.mp4   4s hook clip (over-shoulder terminal)
  clips/trader-monitors-push.mp4  8s wide clip (trader at three monitors)
  work/vo/line01..09.mp3          one voiceover mp3 per script line
  ../../../site/assets/demo.gif   real TUI footage for the product beat

Output: out/the-23m-trader.mp4

Run:  uv run --no-project --with pillow python make_short.py

Caption timing needs no transcription: each script line is its own mp3, so
line durations ARE the caption windows. Beats (visual changes every line,
per shorts-retention practice - see README):
  1 hook clip / 2 leaderboard card / 3 wide clip / 4 punch-in crop /
  5 wide clip / 6 hook clip reprise / 7 $86M card / 8 real TUI / 9 CTA card
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
WORK = HERE / "work"
OVERLAYS = WORK / "overlays"
VO = WORK / "vo"
FINAL = HERE / "out" / "the-23m-trader.mp4"
NIGHT = HERE / "clips" / "night-terminal-push.mp4"
WIDE = HERE / "clips" / "trader-monitors-push.mp4"
TUI_GIF = HERE.parents[2] / "site" / "assets" / "demo.gif"

# ui/theme.py palette - keep in sync
SURFACE = (13, 19, 32)
UP = "#3fcf8e"
AMBER = "#e0af68"
BLUE = "#5b8ef7"
MUTED = "#8a93a6"
WHITE = "#e6e9f0"

# Refresh from https://lb-api.polymarket.com/profit?window=all&limit=5 before
# re-recording the voiceover - captions and audio must state current facts.
# Numbers below pulled 2026-08-14.
LEADERBOARD = [("1", "swisstony", "$23.4M"), ("2", "Theo4", "$22.0M"),
               ("3", "Fredi9999", "$16.6M"), ("4", "RN1", "$12.7M"),
               ("5", "kch123", "$11.4M")]

CAPTIONS = [
    None,  # hook caption is custom-drawn below
    "Meet swisstony - #1\nall-time on Polymarket",
    "The real world\nbecomes a market",
    "Elections. Wars.\nInterest rates.",
    "Shares cost cents.\nRight = $1 each",
    "He's been right.\n$23M worth.",
    "Top 5 accounts:\n$86,000,000+ combined",
    "Watch them tick live\nin your terminal",
    "Free + open source",
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


def build_overlays() -> None:
    OVERLAYS.mkdir(parents=True, exist_ok=True)

    # Hook caption: the number dominates from frame one
    im = Image.new("RGBA", (1080, 440), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def center_line(y, text, fnt, fill):
        w = d.textlength(text, font=fnt)
        d.text(((1080 - w) / 2, y), text, font=fnt, fill=fill)

    center_line(60, "One trader.", bold(54), WHITE)
    center_line(150, "$23,000,000", bold(100), UP)
    center_line(290, "betting on the news", bold(54), WHITE)
    im.save(OVERLAYS / "cap00.png")

    for i, text in enumerate(CAPTIONS):
        if text is None:
            continue
        im = Image.new("RGBA", (1080, 440), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        center_text(d, (540, 200), text, bold(60), WHITE)
        im.save(OVERLAYS / f"cap{i:02d}.png")

    im = Image.new("RGBA", (1080, 280), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    center_text(d, (540, 150), "POLYMARKET / ALL-TIME PROFIT", reg(34), MUTED)
    im.save(OVERLAYS / "toplabel.png")

    im = Image.new("RGBA", (1080, 1080), (*SURFACE, 242))
    d = ImageDraw.Draw(im)
    d.text((90, 110), "ALL-TIME PROFIT LEADERBOARD", font=reg(40), fill=AMBER)
    y = 260
    for rank, name, profit in LEADERBOARD:
        d.text((90, y), rank, font=reg(56), fill=MUTED)
        d.text((190, y), name, font=bold(56), fill=WHITE)
        w = d.textlength(profit, font=bold(56))
        d.text((990 - w, y), profit, font=bold(56), fill=UP)
        y += 150
    im.save(OVERLAYS / "cardA.png")

    im = Image.new("RGBA", (1080, 1080), (*SURFACE, 242))
    d = ImageDraw.Draw(im)
    center_text(d, (540, 380), "TOP 5 COMBINED", reg(48), AMBER)
    center_text(d, (540, 540), "$86,000,000+", bold(130), UP)
    im.save(OVERLAYS / "cardB.png")

    im = Image.new("RGBA", (1080, 1080), (*SURFACE, 255))
    d = ImageDraw.Draw(im)
    center_text(d, (540, 300), "polymarket-tui", bold(96), BLUE)
    center_text(d, (540, 420), "live books / charts / trading", reg(40), MUTED)
    d.rounded_rectangle([70, 540, 1010, 680], radius=16, outline=MUTED, width=3)
    center_text(d, (540, 610), "$ uv tool install polymarket-tui", bold(44), UP)
    center_text(d, (540, 780), "or: brew install byronxlg/tap/polymarket-tui",
                reg(32), MUTED)
    im.save(OVERLAYS / "cardCTA.png")


def main() -> None:
    durs = [probe(VO / f"line{i:02d}.mp3") for i in range(1, 10)]
    starts = [round(sum(durs[:i]), 3) for i in range(len(durs))]
    ends = [round(s + d, 3) for s, d in zip(starts, durs, strict=True)]
    total = round(sum(durs), 3)

    build_overlays()

    with open(WORK / "vo_list.txt", "w") as f:
        for i in range(1, 10):
            f.write(f"file 'vo/line{i:02d}.mp3'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(WORK / "vo_list.txt"), "-c:a", "aac",
                    "-b:a", "160k", str(WORK / "vo_full.m4a")],
                   check=True, capture_output=True, cwd=WORK)

    FINAL.parent.mkdir(exist_ok=True)
    inputs = ["-stream_loop", "1", "-i", str(NIGHT),   # 0: hook (line 1)
              "-i", str(NIGHT),                        # 1: reprise (line 6)
              "-stream_loop", "3", "-i", str(WIDE),    # 2: lines 3 and 5
              "-stream_loop", "3", "-i", str(WIDE),    # 3: punch-in (line 4)
              "-ignore_loop", "0", "-i", str(TUI_GIF)]  # 4: TUI (line 8)
    for i in range(9):
        inputs += ["-i", str(OVERLAYS / f"cap{i:02d}.png")]  # 5..13
    inputs += ["-i", str(OVERLAYS / "cardA.png"),            # 14 (line 2)
               "-i", str(OVERLAYS / "cardB.png"),            # 15 (line 7)
               "-i", str(OVERLAYS / "cardCTA.png"),          # 16 (line 9)
               "-i", str(OVERLAYS / "toplabel.png"),         # 17
               "-i", str(WORK / "vo_full.m4a")]              # 18

    fc = [
        f"color=c=0x0d1320:s=1080x1920:d={total}[base]",
        "[0:v]scale=1080:1080,setsar=1[hook]",
        f"[1:v]setpts=PTS-STARTPTS+{starts[5]}/TB,scale=1080:1080,setsar=1[night2]",
        f"[2:v]setpts=PTS-STARTPTS+{starts[2]}/TB,scale=1080:1080,setsar=1[wideA]",
        # same source, 78% centre crop = punch-in that reads as a cut
        f"[3:v]setpts=PTS-STARTPTS+{starts[2]}/TB,crop=500:500:70:70,"
        "scale=1080:1080,setsar=1[wideB]",
        f"[4:v]fps=24,scale=1080:-2,setsar=1,setpts=PTS-STARTPTS+{starts[7]}/TB[tui]",
        f"[base][hook]overlay=0:280:enable='between(t,0,{ends[0]})'[v0]",
        f"[v0][wideA]overlay=0:280:enable='between(t,{starts[2]},{ends[2]})"
        f"+between(t,{starts[4]},{ends[4]})'[v1]",
        f"[v1][wideB]overlay=0:280:enable='between(t,{starts[3]},{ends[3]})'[v2]",
        f"[v2][night2]overlay=0:280:enable='between(t,{starts[5]},{ends[5]})'[v3]",
        f"[v3][tui]overlay=0:493:enable='between(t,{starts[7]},{ends[7]})'[v4]",
        f"[v4][14:v]overlay=0:280:enable='between(t,{starts[1]},{ends[1]})'[v5]",
        f"[v5][15:v]overlay=0:280:enable='between(t,{starts[6]},{ends[6]})'[v6]",
        f"[v6][16:v]overlay=0:280:enable='between(t,{starts[8]},{total})'[v7]",
    ]
    prev = "v7"
    for i in range(9):
        fc.append(f"[{prev}][{i + 5}:v]overlay=0:1440:"
                  f"enable='between(t,{starts[i]},{ends[i]})'[c{i}]")
        prev = f"c{i}"
    fc.append(f"[{prev}][17:v]overlay=0:0[vout]")

    subprocess.run(["ffmpeg", "-y", *inputs,
                    "-filter_complex", ";".join(fc),
                    "-map", "[vout]", "-map", "18:a",
                    "-t", str(total), "-r", "24",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(FINAL)], check=True)
    print(f"wrote {FINAL} ({total}s)")


if __name__ == "__main__":
    main()
