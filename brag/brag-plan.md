# Brag Plan: polymarket-tui

## What is this app?
A fast, keyboard-driven terminal client for Polymarket: browse markets, watch live
order books and trades, chart prices, track P&L, and place orders without leaving
the terminal. Orders are dry-run until you explicitly go LIVE.

## The angle
A real exchange, rendered in text. No mockups: every product frame in the video is a
frame from the recorded demo session already on the landing page (`site/assets/demo.gif`,
redacted `demo-trader`, balances hidden). The video opens the way the product opens,
with a shell prompt, and ends with the install line.

## Hook (first 2-3 seconds)
A prompt types `polymarket-tui`, then the landing page headline rises in:
"Polymarket in your terminal_".

## Key moments (the middle)
- The market screen: YES/NO chips, a live order book with depth bars, the trade tape,
  the price chart. Slow push toward the book.
- Order entry under the book: `BUY 100 YES @ 32.5c (limit GTC)`, cost line, `[DRY]`.
- The dry-run toast: `DRY RUN: BUY 100 YES @ 32.5c (LIMIT GTC) signed, not posted`.

## Outro / punchline
`>_ polymarket-tui`, then `uv tool install polymarket-tui` types out, then the site URL.

## User flow worth showing
Open a market -> cursor the live book -> place a buy (dry-run: signed, never posted).
Taken straight from the recorded session, frames 25, 31 and 49 of the demo GIF.

## Tone
- Preset: polished
- Creative direction: a quiet product film for a real trading tool
- Interpretation: 4 scenes, long holds, soft crossfades, no jokes, product copy verbatim.

## Format: landscape - 1920x1080
## Duration: 20s

## Visual identity (from the project)
- Background: #0a0e14 (--bg), panels #0d1219 (--bg-2), rules #1b232e / #29323f
- Accent: #4d8bf5 (--accent); amber #d9a032 for DRY; green #41b866; red #e05a51
- Text: #c9d3df (--ink), secondary #828f9e (--dim)
- Display font: IBM Plex Mono 600 (vendored woff2 from site/assets/fonts)
- Body font: IBM Plex Mono 400/500
- Strongest visual element: the market screen with the red/green depth bars of the book

## Share copy (draft)
Introducing polymarket-tui: Polymarket in your terminal. Live books, charts, P&L and
order entry, all keyboard, no browser. Dry-run by default. Python, MIT.

## Audio direction
- Role: warm bed, sparse professional accents
- Music: happy-beats-business-moves-vol-12 (steady and clean, the polished pick)
- Music treatment: starts at 0 at 0.30, fades out over the last 1.8s
- Music cue guidance: preset read (109.96 BPM). Strong cues in window: 8.74, 10.93,
  13.11, 17.47, 18.56. Beat grid for entrances: 1.64, 2.19, 4.39, 5.34, 10.37, 16.38.
- Audio-reactive treatment: subtle; music RMS breathes the terminal window's glow and
  the wordmark glow. No waveform or equalizer visuals.
- SFX posture: sparse. Key ticks under the two typed lines, one soft drop when the
  terminal window lands, one soft drop on the dry-run cut, one bong under the wordmark.
- Audio-coupled moments: typed prompt, typed install line, window landing, dry-run cut.
- Restraint rule: nothing louder than the music; no SFX on the label copy.

## Storyboard

### Scene 1 - Hook - 4.4s (0.0-4.4)
Black-blue background. `~ $` prompt, `polymarket-tui` types out (key ticks), caret.
Headline "Polymarket in your terminal_" rises at 2.19 (beat) and holds; sub line
"all keyboard, no browser" at 2.9.
Sequential/interaction: typed text, character by character.
Audio intent: quiet start, ticks on keys, music under.
Transition mood: soft crossfade -> Scene 2

### Scene 2 - The book - 6.0s (4.2-10.4)
Terminal window (title bar "polymarket-tui - recorded session") with the market screen
frame (book.png). Lands at 4.39 with a soft drop; slow push-in toward the order book.
Label top-left at 5.34: "Live order books, straight from the CLOB." Holds 5s.
Sequential/interaction: none (push-in only).
Audio-coupled idea: window landing on the beat.
Transition mood: soft crossfade -> Scene 3

### Scene 3 - Order entry, dry-run - 5.6s (10.2-15.8)
Same window, order.png. Label at 10.93 (strong cue): "Orders in cents, under the live
book." At 13.11 (strong cue) the frame hard-cuts to dryrun.png (the toast) with a soft
drop; label becomes "Dry-run by default: signed, never posted." Holds 2.7s.
Sequential/interaction: two states, cut on the cue.
Transition mood: soft crossfade -> Scene 4

### Scene 4 - Outro - 4.4s (15.6-20.0)
`>_ polymarket-tui` wordmark scales in at 16.38 (beat, bong). `uv tool install
polymarket-tui` types at 17.47 (strong cue, key ticks). URL fades in at 18.56.
Music fades out.
Sequential/interaction: typed install line.

**Music mood for this video:** steady, clean, corporate-adjacent, quiet.
**Audio summary:** a low bed with key ticks at the two typed lines, two soft drops on
the product cuts, one bong under the wordmark, then a fade to silence.
