# Landing page (static, GitHub Pages)

A single static page (`index.html`) plus `assets/`. Its hero plays a **recorded
terminal session** of the TUI (browse -> open a market -> cursor the live book
-> chart -> search) using [asciinema](https://asciinema.org) - a small JS player
plus a `.cast` text file, both vendored, no external CDN and no server.

Deployed to GitHub Pages by `.github/workflows/pages.yml` on push to `main`.
Live URL (once Pages is enabled): https://byronxlg.github.io/polymarket-tui/

## Files

```
site/
  index.html                        the page (references assets/* with relative paths)
  assets/
    asciinema-player.min.js         vendored player (Apache-2.0)
    asciinema-player.css            vendored player styles
    demo.cast                       the recording (asciinema v2 format)
scripts/
  record_demo.sh                    re-records assets/demo.cast
  trim_cast.py                      trims dead time from a raw cast
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

`record_demo.sh` runs the app under a throwaway `HOME`, so the recording is
**anonymous/DRY** - no wallet, no balance, no LIVE, public data only. It scripts
the keystroke tour with `tmux send-keys`; edit the `K ...; sleep ...` lines to
change the tour, adjust `COLS`/`ROWS` for the terminal size, then re-run. The
raw cast is trimmed by `trim_cast.py` (drops the initial load gap, clamps long
idle gaps) into `assets/demo.cast`. Reload the page to see it.

Playback options (autoplay, loop, poster frame, theme) live in the
`AsciinemaPlayer.create(...)` call at the bottom of `index.html`.

## Update the player assets

```sh
npm pack asciinema-player@<version>
tar -xzf asciinema-player-*.tgz
cp package/dist/bundle/asciinema-player.min.js site/assets/
cp package/dist/bundle/asciinema-player.css    site/assets/
```

## Deploy

Push to `main`; the Pages workflow uploads `site/` and deploys it. The first run
enables Pages automatically (`actions/configure-pages` with `enablement: true`).
The cast is ~7 MB uncompressed but ~170 KB gzipped; GitHub Pages serves it
gzipped. All asset paths are relative, so the project-subpath URL
(`/polymarket-tui/`) works without changes.
