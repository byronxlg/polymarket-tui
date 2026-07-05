# Visual evaluation harness

Text-scraping tmux panes misses what users see: layout voids, broken
charts, clipped columns, crashes that only show as a traceback screen.
The harness renders the real running app to PNG images for review.

## Pieces

- `scripts/tui_snap.py` - screenshot one tmux pane:
  `uv run python scripts/tui_snap.py -L pmtui -o /tmp/shot.png`
  Captures ANSI (`capture-pane -ep`), renders via rich -> SVG, rasterizes
  with resvg (`brew install resvg`).
- `scripts/tui_journey.py` - drive a scripted user journey and screenshot
  every step: `uv run python scripts/tui_journey.py journeys/browse.json -o /tmp/shots`
  Boots a fresh app in an isolated tmux server (`-L pmtui-journey`),
  sends keys step by step. `--size 120x35` overrides terminal size.
- `journeys/*.json` - step scripts: `[name, [keys...], wait_seconds]`.
  Keys use tmux send-keys names (Down, Enter, Escape, Space, literal
  chars). Journeys assume live API data has loaded (`boot_wait`).
- `scripts/journey_env.sh <anon|authed-dry>` - prepares an isolated HOME
  so a journey can never trade for real; journey JSONs launch the app
  through it via their `command` field. The persona journey catalog and
  its grading log live in docs/user-journeys.md.

## Review discipline

Review the PNGs like a user, not like a diff: look for dead space,
unreadable truncation, inconsistent number formats, flat/broken charts,
columns that add nothing, footer keys that lie. File a GH issue per
finding. Re-run the journey after a fix and compare.

Journeys run against live Polymarket data through the real app - prices
and markets differ run to run; layout and behavior are what's under test.
