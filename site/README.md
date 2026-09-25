# Landing page (static, GitHub Pages)

A single static page (`index.html`) plus `assets/`. Its hero plays the
**20-second launch video** (`assets/brag.mp4`) and nothing else: one recording,
autoplaying, muted, looped. The video is cut from stills of a recorded terminal
session (browse -> star a watchlist -> open a market -> dry-run buy -> cursor
the live book -> a public trader's profile -> search) kept in
`assets/demo.cast`. The page itself is static: no CDN, no server, no player.

The cast used to be played on the page by a vendored
[asciinema](https://asciinema.org) player below the video. That second,
duplicate recording was removed (two moving recordings of the same session);
the cast stays because the README's hero GIF and the launch video's stills are
both made from it.

Deployed to GitHub Pages by `.github/workflows/pages.yml` on push to `main`.
Live URL (once Pages is enabled): https://polymarket-tui.botsmith.dev/

## Files

```
site/
  index.html                        the page (references assets/* with relative paths)
  assets/
    asciinema-player.min.js         vendored player (Apache-2.0); no longer loaded by the page
    asciinema-player.css            vendored player styles; no longer loaded by the page
    demo.cast                       the recording (asciinema v2 format): source of demo.gif and the brag stills
    demo-poster.png                 unused since the player was removed; kept, referenced by nothing
    og.png                          generated: 1200x630 social preview card (og:image)
    brag.mp4 / brag.jpg             launch video and its poster, made with the /brag skill (see below)
    fonts/plexmono-*.woff2          vendored IBM Plex Mono, latin subset (OFL)
scripts/
  record_demo.sh                    re-records assets/demo.cast
  trim_cast.py                      trims dead time from a raw cast
  redact_cast.py                    strips account identity from the cast
  make_site_images.py               regenerates og.png from the page
```

## Preview locally

It is fully static - open `index.html` directly, or serve the folder:

```sh
python3 -m http.server -d site 8000     # http://localhost:8000
```

## Re-record the demo (after the UI changes)

```sh
uv sync                             # ensure the app + deps are current
uv tool install asciinema           # one-time, if missing
bash scripts/record_demo.sh         # drives the app in tmux, writes site/assets/demo.cast
```

The cast is no longer played on the page, but it is still the footage the
launch video and the README GIF are cut from, so keep it current.

`record_demo.sh` records **authed in DRY** so the order-entry scene is real:
`journey_env.sh authed-dry` builds an isolated `HOME` with the credentials
copied and `execution_live` forced false (an order is signed, never posted),
and `POLYMARKET_HIDE_BALANCES=1` masks the header cash/pf and any own-position
numbers at the source. After `trim_cast.py` tightens dead time,
`redact_cast.py` rewrites the profile name/funder in the cast and **refuses to
write the file if any identity or balance string survived** - so a leak fails
the run instead of shipping. It scripts the keystroke tour with
`tmux send-keys`; edit the `K ...; sleep ...` lines to change the tour, adjust
`COLS`/`ROWS` for the terminal size, then re-run (set `SNAP_DIR=...` to dump a
pane snapshot per scene for review). Reload the page to see it.

After re-recording, regenerate everything derived from the cast - the README's
hero GIF and the launch video's terminal stills - and the og card, which is a
screenshot of the hero:

```sh
uv run --with playwright python scripts/make_site_images.py     # og.png
agg --font-size 14 --speed 2 --fps-cap 4 --theme asciinema \
    site/assets/demo.cast site/assets/demo.gif                  # README hero (brew install agg)
uv run --with playwright python scripts/make_brag_stills.py     # brag/composition/assets/ui/*.png
```

## Regenerate the launch video

The 20-second launch video on the landing page and in the README is made with the
`/brag` skill (Hyperframes, local render). Run `/brag` in the repo; the plan, the
composition and the render land in `brag/` (`brag/brag.mp4`, `brag/brag.jpg`). The
composition holds on three stills of the recorded demo, so a UI change means:
re-record the demo, run `make_brag_stills.py`, then re-render the existing
composition (`cd brag/composition && npx hyperframes check && npx hyperframes render`)
- a full `/brag` rerun is only needed when the story changes. Copy `brag/brag.mp4`
and `brag/brag.jpg` to `site/assets/`, keeping the mp4 near 2 MB (the renders/ output
is re-encoded with `ffmpeg -crf 28 -preset slow`; the poster is a frame at 7.6 s).

## The vendored asciinema player

`assets/asciinema-player.min.js` and `assets/asciinema-player.css` are still in
the repo but are loaded by no page. They are kept in case an interactive
recording is ever wanted again; refresh them with:

```sh
npm pack asciinema-player@<version>
tar -xzf asciinema-player-*.tgz
cp package/dist/bundle/asciinema-player.min.js site/assets/
cp package/dist/bundle/asciinema-player.css    site/assets/
```

## Deploy

Push to `main`; the Pages workflow uploads `site/` and deploys it. The first run
enables Pages automatically (`actions/configure-pages` with `enablement: true`).
The page now fetches the 2 MB launch video and not the cast. All asset paths
are relative, so the project-subpath URL
(`/polymarket-tui/`) works without changes.
