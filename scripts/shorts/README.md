# Vertical shorts

Renders a 1080x1920 video of the real TUI for TikTok / Reels / Shorts.

```sh
bash scripts/shorts/record.sh scripts/shorts/beats/<sheet>.json out/
uv run python scripts/shorts/render.py scripts/shorts/beats/<sheet>.json out/
```

Requires `asciinema`, `tmux`, `ffmpeg`, `jq`, Pillow + pyte (dev group), and
real credentials (or `SHORTS_MODE=anon` to record signed out - what CI does).
Produces `out/<slug>.mp4`.

`scripts/shorts/pick_story.py out/` picks the day's story from live Gamma
data and emits the beat sheet; `.github/workflows/daily-short.yml` runs the
whole chain daily and delivers the mp4 to Telegram for review. Posting stays
manual (see Publishing).

## Why it is built this way

**The terminal is never recorded at phone aspect.** Below ~100 columns the
market screen falls apart: the order book collapses to a vertical `OR/DE/R`
label with no rows, the YES/NO chips crush to `Y`/`N`, and the outcome rail
clips prices mid-number. So `record.sh` captures at 120x38 - the narrowest
geometry where the full layout survives - and `render.py` centres that native
aspect in the vertical frame, with the market question above and captions
below. Roughly 900px of every frame is band rather than footage; that is the
format, not wasted space.

**Captions are burned in.** Nearly all of this is watched muted, and every
platform renders (or drops) an uploaded subtitle track differently.

**Text is drawn with Pillow, not ffmpeg `drawtext`.** Homebrew's ffmpeg ships
without libfreetype, so `drawtext` does not exist on this machine.

**The terminal is rasterized by `rasterize.py` (pyte + Pillow), not agg.**
agg's terminal emulation diverges from a real terminal on this app: screens
that blank large regions (search results, the event screen's chart plot) keep
ghost text from the previous screen. tmux and pyte replay the identical byte
stream cleanly, so agg was replaced. The event screen is still only used as a
transient hop in beat sheets - see pick_story.py.

**Pan mode** (`"pan": true` plus per-beat `"focus": left|mid|right`) crops the
near-native-resolution terminal to a canvas-width window and eases between
focus points per beat. Full-frame scaling leaves ~9px glyphs, unreadable on
phones; the crop keeps them ~50% larger and the pans add motion.

**One clock.** `record.sh` waits for a fully painted home screen, then records
`head_offset` - the point the beat clock starts from - into the timings file.
`render.py` cuts there. Anchoring the cut on anything else (say, the first
frame containing a price) lands mid-boot and desyncs every caption.

**The head is zeroed, not dropped.** A cast is a stream of incremental
terminal writes, so the boot events *are* the paint. Deleting them opens the
video on an empty terminal that only fills in as later writes arrive; setting
their duration to zero replays the paint instantly instead.

## Safety

Same guarantees as `record_demo.sh`: runs authed in DRY under an isolated HOME
(`journey_env.sh authed-dry` forces `execution_live = false`) with
`POLYMARKET_HIDE_BALANCES=1`, then `redact_cast.py` rewrites the profile name
and funder and fails the run if anything survived. A short can never place an
order and can never ship real balances.

One judgement call is not automated: expanding the trade tape (`a`) pulls a
named trader's wallet and open positions into the cursor rail. That is public
Polymarket data, but foregrounding one person's portfolio in promotional
content is a different context from showing it in the app, so beat sheets end
on the book or the chart instead.

## Beat sheets

`beats/*.json`. Each beat is a caption plus optional `type` (literal text,
sent first) and `keys` (tmux key names), then `wait` seconds:

```json
{ "caption": "The order book streams live", "keys": ["Down", "Down"], "wait": 3.4 }
```

Captions must never hardcode a price - the market moves between writing the
sheet and recording it.

Sheet-level flags:

| flag | default | effect |
| --- | --- | --- |
| `clamp_lag` | `true` | cut idle stretches down to `MAX_GAP` (0.85s) |
| `timer` | `false` | burn in an elapsed-seconds counter, top right |
| `trim_boot` | `true` | start at the settled home screen rather than at launch |
| `boot_caption` | - | caption for the pre-ready stretch when `trim_boot` is off |

Clamping remaps every caption through the same time map that produced the
footage, so cutting lag can never slide a caption off the frame it labels.

`timer` forces `clamp_lag` off. A clamped video no longer runs at wall-clock
speed, so a counter over it would either overstate elapsed time or visibly
jump wherever lag was cut. The counter states true elapsed time since the
process launched - which is also why the speed sheet keeps the real boot. It
still includes whatever reading pauses the sheet asks for, so it is honest
about that journey, not a benchmark of the tool.

## The three sheets

- `cold-start-speed` - launch to a streaming order book, counter running
- `dry-trade` - the money path: cursor the book, `b`, size, review, place in DRY
- `hormuz-term-structure` - one question priced at six dates, and the slide

## Publishing

Not automated, and not close to it. Autonomous posting is gated on a separate
manual review per platform: YouTube forces uploads from unaudited API projects
to private (and revokes OAuth refresh tokens every 7 days while the app sits
in Testing), TikTok forces direct posts to `SELF_ONLY` until its Content
Posting audit passes, and Instagram Reels publishing needs Meta app review.
Each review wants a demo of a working product - which is what this pipeline
produces. Post by hand until those clear.
