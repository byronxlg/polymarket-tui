# Hyperframes Composition Brief: polymarket-tui

## Objective
Create a short launch-style brag video for polymarket-tui.

## Output
- Composition directory: `brag/composition/`
- Rendered video: `brag/brag.mp4`
- Format: landscape - 1920x1080, 30 fps
- Duration: 20 seconds

## Source Material
- Project root: repo root (byronxlg/polymarket-tui)
- Primary files read: README.md, site/index.html, site/README.md, docs/marketing.md,
  site/assets/demo.gif (frames), demo-poster.png
- Product name: polymarket-tui
- Tagline / strongest claim: "Polymarket in your terminal" / "all keyboard, no browser"
- Key UI moment to show: the market screen (live order book with depth bars), order
  entry under the book, the dry-run toast. Real frames from the recorded demo, no
  invented UI: `assets/ui/book.png`, `assets/ui/order.png`, `assets/ui/dryrun.png`.
- Copy that must appear verbatim:
  - Polymarket in your terminal_
  - all keyboard, no browser
  - uv tool install polymarket-tui
  - polymarket-tui.botsmith.dev

## Creative Direction
- Tone preset: polished
- Creative direction: a quiet product film for a real trading tool
- Interpretation: 4 scenes, long holds, 0.6s crossfades, no jokes
- Angle: real exchange rendered in text; every product frame is from the real session
- Hook: prompt types `polymarket-tui`, headline rises
- Outro: wordmark, install line, URL
- Avoid: generic SaaS language, abstract filler, redesigning the UI

## Visual Identity
- Background: #0a0e14; panels #0d1219; rules #1b232e / #29323f
- Text: #c9d3df; secondary #828f9e
- Accent: #4d8bf5; DRY amber #d9a032
- Display font: IBM Plex Mono 600 (assets/fonts/plexmono-600.woff2)
- Body font: IBM Plex Mono 400 / 500
- Visual references: the landing page's `.term` window (1px #29323f border, 6px radius,
  #0d1219 bar with a red dot and "recorded session"), the `~ $` prompt with accent

## Storyboard
Use the storyboard in `brag/brag-plan.md` as the creative contract.
1. Hook - 4.4s - typed prompt, headline, sub line
2. The book - 6.0s - terminal window with book.png, push-in, one label
3. Order entry, dry-run - 5.6s - order.png, cut to dryrun.png on 13.11, two labels
4. Outro - 4.4s - wordmark, typed install line, URL, music fade

## Audio
- Audio role: warm bed, sparse accents
- Audio arc: quiet in, ticks, two soft drops on product cuts, bong under the wordmark, fade
- Music: assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3 at 0.30
- Music treatment: volume lane fade-out 18.2 -> 20.0
- Music cue guidance: bundled preset (vol-12, 109.96 BPM); strong cues 10.93, 13.11,
  17.47, 18.56; beats 2.19, 4.39, 5.34, 10.37, 16.38
- Audio-reactive treatment: subtle; per-frame RMS from assets/audio-data.js drives the
  window glow (scenes 2-3) and wordmark glow (scene 4)
- Audio-coupled moments: typed prompt (key ticks), window landing (drop_001),
  dry-run cut (drop_001), wordmark (bong_001), install line (key ticks)
- SFX guidance: low high-frequency-risk files only; SFX 0.45-0.6, under the music
- Audio files: copied into `brag/composition/assets/`

## Hyperframes Instructions
Standalone composition, single paused GSAP timeline registered at
`window.__timelines["brag"]`, root `data-duration="20"`. Run `npx hyperframes check`
before render.
