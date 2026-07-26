# Vertical shorts

Renders a 1080x1920 video of the real TUI for TikTok / Reels / Shorts.

```sh
bash scripts/shorts/record.sh scripts/shorts/beats/<sheet>.json out/
uv run python scripts/shorts/render.py scripts/shorts/beats/<sheet>.json out/
```

Requires `asciinema`, `tmux`, `agg`, `ffmpeg`, `jq`, Pillow (dev group), and
real credentials. Produces `out/<slug>.mp4`.

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

## Publishing

Not automated, and not close to it. Autonomous posting is gated on a separate
manual review per platform: YouTube forces uploads from unaudited API projects
to private (and revokes OAuth refresh tokens every 7 days while the app sits
in Testing), TikTok forces direct posts to `SELF_ONLY` until its Content
Posting audit passes, and Instagram Reels publishing needs Meta app review.
Each review wants a demo of a working product - which is what this pipeline
produces. Post by hand until those clear.
