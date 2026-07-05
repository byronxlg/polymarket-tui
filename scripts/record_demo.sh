#!/usr/bin/env bash
# Record the landing-page demo cast (asciinema) of the TUI.
#
# Produces src/polymarket_tui/web/static/demo.cast - a scripted tour of the
# browse -> market -> book -> chart -> search flow. Runs the app under a throwaway
# HOME so it starts anonymous/DRY (no wallet, no LIVE, public data only), then
# trims dead time so playback is tight.
#
# Requires: asciinema (uv tool install asciinema), tmux. Re-run any time the UI
# changes to refresh the demo, then rebuild the page (see web/DEMO.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/src/polymarket_tui/web/static/demo.cast"
RAW="$(mktemp -t pmtui-demo-XXXX).cast"
REC_HOME="$(mktemp -d -t pmtui-home-XXXX)"
SOCK="pmtui-rec"
COLS=118
ROWS=32
APP="$ROOT/.venv/bin/python -u -m polymarket_tui"

command -v asciinema >/dev/null || { echo "asciinema not found: uv tool install asciinema"; exit 1; }
command -v tmux >/dev/null || { echo "tmux not found"; exit 1; }

echo "Recording to $RAW (home=$REC_HOME, ${COLS}x${ROWS})..."
tmux -L "$SOCK" kill-server 2>/dev/null || true
tmux -L "$SOCK" new-session -d -x "$COLS" -y "$ROWS" -e HOME="$REC_HOME" \
  "asciinema rec '$RAW' --overwrite -q -c '$APP'"

K() { tmux -L "$SOCK" send-keys "$@"; }

sleep 15                                   # first paint (fetches live markets)
# Browse the trending list, cycle a couple of categories.
K Down; sleep 0.5; K Down; sleep 0.5; K Down; sleep 0.5; K Down; sleep 0.7
K Tab; sleep 1.8                           # -> Politics
K Tab; sleep 1.8                           # -> Sports
K Tab; sleep 1.6                           # -> Crypto
K Up; sleep 0.4; K Up; sleep 0.6           # back to the top of the list
# Open an event, then a market.
K Enter; sleep 3.0
K Enter; sleep 3.5
# Cursor through the live order book, then back up to the outcomes.
K Down; sleep 0.7; K Down; sleep 0.7; K Down; sleep 0.7; K Down; sleep 0.9
K Up; sleep 0.6; K Up; sleep 0.9
# Cycle the chart timeframe.
K Tab; sleep 1.6; K Tab; sleep 1.6
# Step back out and search.
K Escape; sleep 1.2
K Escape; sleep 1.2
K "/"; sleep 1.0
K "bitcoin"; sleep 2.0
K Escape; sleep 1.0
K "q"; sleep 2.0
tmux -L "$SOCK" kill-server 2>/dev/null || true

echo "Trimming dead time -> $OUT"
python3 "$ROOT/scripts/trim_cast.py" "$RAW" "$OUT"
rm -rf "$RAW" "$REC_HOME"
echo "Done: $OUT ($(wc -c < "$OUT") bytes)"
