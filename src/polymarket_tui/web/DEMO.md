# Landing page + demo video

The landing page (`templates/landing.html`) is a static page whose hero plays
a **recorded terminal session** of the TUI (browse -> open a market -> cursor
the live book -> chart -> search). It is served by `polymarket-tui-web`, but
the page and its assets are fully static and can be dropped onto any static
host (GitHub Pages, Cloudflare/Netlify Pages, S3 + CDN) unchanged.

The recording is [asciinema](https://asciinema.org): a small JS player plus a
`.cast` text file, both vendored under `static/` - no server, no external CDN.

## See it locally

```sh
uv run polymarket-tui-web            # http://localhost:8000
```

- `/`     landing page with the demo playing in the hero
- `/app`   the real, interactive TUI (needs the server; not part of the static bundle)

Custom port: `PMTUI_WEB_PORT=8771 uv run polymarket-tui-web`.

## Files

```
web/
  templates/landing.html            the page (loads assets/* with relative paths)
  static/
    asciinema-player.min.js         vendored player (Apache-2.0)
    asciinema-player.css            vendored player styles
    demo.cast                       the recording (asciinema v2 format)
scripts/
  record_demo.sh                    re-records demo.cast
  trim_cast.py                      trims dead time from a raw cast
```

## Re-record the demo (after the UI changes)

```sh
uv sync                             # ensure the app + deps are current
uv tool install asciinema           # one-time, if missing
bash scripts/record_demo.sh         # drives the app in tmux, writes static/demo.cast
```

`record_demo.sh` runs the app under a throwaway `HOME`, so the recording is
**anonymous/DRY** - no wallet, no balance, no LIVE, public data only. It scripts
the keystroke tour with `tmux send-keys`; edit the `K ...; sleep ...` lines to
change the tour, adjust `COLS`/`ROWS` for the terminal size, then re-run. The
raw cast is trimmed by `trim_cast.py` (drops the initial load gap, clamps long
idle gaps) into `static/demo.cast`.

Reload `/` to see the new recording. To tweak playback (autoplay, loop, font
size, theme, poster frame), edit the `AsciinemaPlayer.create(...)` options at
the bottom of `landing.html`.

## Update the player assets

```sh
npm pack asciinema-player@<version>
tar -xzf asciinema-player-*.tgz
cp package/dist/bundle/asciinema-player.min.js web/static/
cp package/dist/bundle/asciinema-player.css    web/static/
```

## Deploy as a static site

Publish `web/templates/landing.html` as `index.html` alongside the `static/`
directory served at `/assets/` (the page references `assets/asciinema-player.css`,
`assets/asciinema-player.min.js`, `assets/demo.cast` with relative paths). The
"Launch in browser" buttons point at `/app`, which only exists when the
`polymarket-tui-web` server is running - drop or repoint them for a
server-less deployment.

The cast is ~7 MB uncompressed but ~170 KB gzipped; serve it with gzip/brotli.
```
