# AI-clip shorts

Clickbait-style vertical short: AI-generated b-roll for the story, real TUI
footage for the product beat, install CTA to close. First produced
2026-08-14 ("The $23M Trader", `out/the-23m-trader.mp4`). Deliberately
manual - no automation yet.

This sits beside the sibling pipeline in `scripts/shorts/` (which records
the real TUI); it borrows its brand rules (theme colors, JetBrains Mono,
Pillow-drawn text - ffmpeg drawtext does not exist on this machine) but is
otherwise standalone.

## The pipeline, step by step

### 1. Story - real numbers only

The hook must be true. Pull the all-time profit leaderboard:

```sh
curl -s "https://lb-api.polymarket.com/profit?window=all&limit=5"
```

(2026-08-14: swisstony $23.4M, Theo4 $22.0M, Fredi9999 $16.6M, RN1 $12.7M,
kch123 $11.4M; top five $86M+.) Refresh before re-recording - numbers in
the voiceover and cards must match the live data at publish time. Same
"state facts" rule as the app: no invented or projected figures.

Foregrounding a named trader in promotional content is a judgement call
(see `../README.md` Safety) - leaderboard pseudonyms are public and
aggregate profit is the least invasive stat; do not show their positions.

### 2. Script - every line must grab

Rules that survived iteration (v5):

- The number leads: bold claim in the first second, context after.
- Every line is a fragment, question, or open loop. No explainer prose:
  "The game? The real world becomes a market." not "Prediction markets
  let you buy shares in real-world outcomes."
- One line = one beat = one visual = one caption. 9 lines, 35-45s total.
- The product pivot is framed as a reveal ("Now the twist: ...") and the
  last two lines are the funnel: real TUI footage, then install CTA.
- Write "Polymarket T U I" for TTS so it spells the letters.

Retention research behind this (Aug 2026): viewers decide in ~1.7s; visual
change every few seconds; front-load the payoff. Sources pinned in the PR
that added this file.

### 3. Voiceover - one mp3 per line

Render each script line as its own mp3: line durations then give exact
caption windows with no transcription/whisper step. OpenAI TTS via the
local say.sh skill (Doppler-authed), voice `ash`, speed 1.15, tone
"energetic, punchy short-form documentary narrator; builds excitement,
lands the numbers hard":

```sh
~/.claude/skills/tts/scripts/say.sh --text "<line>" --voice ash \
  --speed 1.15 --tone "<tone above>" --name line01
```

Render sequentially - a parallel burst of 10 calls hit 429s. Copy results
to `work/vo/line01..09.mp3`. Free fallback (noticeably worse):
`uvx edge-tts --voice en-US-ChristopherNeural --rate=+8% --text ... --write-media ...`.

### 4. AI clips - the reusable b-roll in clips/

Generated with Seedance 2.0 Fast (via DaVinci), 4-8s each. Committed
learning:

- Generate at 9:16 and 720p+ if offered. The current clips are 1:1 480p
  and go soft upscaled to 1080 - acceptable, not great.
- Never ask the model for readable text; prompt "no readable words on
  screen". Tiny/bokeh digits look right, crisp digits come out garbled.
  Real numbers go on Pillow cards instead.
- Match the app palette in the prompt (deep navy, green/red digits, one
  blue accent) so footage and cards feel like one thing.

Prompts used for the two clips on hand:

`clips/night-terminal-push.mp4` (4s, the hook):
> Vertical 9:16. Night. Slow cinematic push-in over the shoulder of a
> person in a dark room, facing a large monitor that fills the frame with
> a deep navy terminal interface: dense rows of tiny green and red
> numbers, thin sparkline charts, one bright blue highlight bar, a
> blinking block cursor. The screen glow rims their silhouette. Shallow
> depth of field, teal and amber palette, no readable words on screen.

`clips/trader-monitors-push.mp4` (8s, mid-section):
> Vertical 9:16. Slow cinematic push-in through a dark home office at
> night. A man sits with his back to camera, silhouetted against three
> glowing monitors covered in green and red charts. City lights out the
> window. Moody, shallow depth of field, teal and amber palette. No
> on-screen text.

Still wanted: a macro screen-texture clip (prompt in session notes) to
replace the second use of the wide clip.

### 5. Assembly

```sh
uv run --no-project --with pillow python make_short.py
```

`make_short.py` is self-contained: draws all overlays (captions, cards,
top label), concats the voiceover, and runs one ffmpeg pass. Layout:
1080x1920, navy base, footage in a 1080x1080 slot at y=280, captions at
y=1440. Visual changes every line; the mid-section fakes an extra cut with
a 78% punch-in crop of the same clip. Cost per video: cents (TTS) once the
clips exist.

### 6. Verify before sending

Extract frames and look at them - do not trust the filter graph:

```sh
ffmpeg -ss <t> -i out/the-23m-trader.mp4 -frames:v 1 frame.png
```

Check: hook caption on frame one, cards legible, captions in sync at line
boundaries, TUI beat readable, CTA card correct.

### 7. Deliver

Telegram for review (same as the daily short):

```sh
doppler run --project global --config home -- bash -c \
  'curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendVideo" \
    -F chat_id=8851680837 -F video=@out/the-23m-trader.mp4 \
    -F supports_streaming=true'
```

Posting is manual per platform (see `../README.md` Publishing). Extra risk
specific to this format: platforms penalize fully-synthetic "faceless"
content; the mitigations are real data, real TUI footage, and the real
product CTA.

## Files

- `clips/` - reusable AI b-roll (gitignored; back up outside the repo)
- `out/` - finished cuts (gitignored)
- `work/` - voiceover lines + generated overlays (gitignored, transient)
- `make_short.py` - the assembler; captions, cards, and beat map live here

Media is gitignored, so a fresh clone has documentation and assembler but
no footage: regenerate clips from the prompts above, re-render voiceover
from the script in `make_short.py` captions plus the pinned VO lines, or
copy `clips/` from the machine that has them.
