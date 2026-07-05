#!/usr/bin/env bash
# Record the landing-page demo cast (asciinema) of the TUI.
#
# Produces site/assets/demo.cast - a scripted tour: browse -> star rows ->
# watchlist -> market -> live book -> BUY entry placed in DRY -> a public
# trader's profile -> search. Runs authed in DRY under an isolated HOME
# (journey_env.sh authed-dry: creds copied with execution_live forced false)
# with POLYMARKET_HIDE_BALANCES=1 so no real numbers render; redact_cast.py
# then rewrites the profile name/funder and refuses to ship a leak.
#
# Requires: asciinema (uv tool install asciinema), tmux, real credentials in
# ~/.config/polymarket-tui/credentials.toml. Re-run any time the UI changes,
# then reload the page (see site/README.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/site/assets/demo.cast"
RAW="$(mktemp -t pmtui-demo-XXXX).cast"
TRIMMED="$(mktemp -t pmtui-demo-trim-XXXX).cast"
SOCK="pmtui-rec"
COLS=160
ROWS=42
APP="$ROOT/.venv/bin/python -u -m polymarket_tui"
SNAP_DIR="${SNAP_DIR:-}"        # optional: capture pane text per scene for review

command -v asciinema >/dev/null || { echo "asciinema not found: uv tool install asciinema"; exit 1; }
command -v tmux >/dev/null || { echo "tmux not found"; exit 1; }

REC_HOME="$("$ROOT/scripts/journey_env.sh" authed-dry)"
FUNDER="$(python3 -c "
import tomllib, sys
print(tomllib.load(open('$REC_HOME/.config/polymarket-tui/credentials.toml', 'rb'))['funder'])")"
NAME="$(curl -sf -A Mozilla/5.0 "https://gamma-api.polymarket.com/public-profile?address=$FUNDER" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('name') or d.get('pseudonym') or '')" \
  || true)"

echo "Recording to $RAW (home=$REC_HOME, ${COLS}x${ROWS}, authed DRY, balances hidden)..."
tmux -L "$SOCK" kill-server 2>/dev/null || true
tmux -L "$SOCK" new-session -d -x "$COLS" -y "$ROWS" \
  -e HOME="$REC_HOME" -e POLYMARKET_HIDE_BALANCES=1 \
  "asciinema rec '$RAW' --overwrite -q -c '$APP'"

K() { tmux -L "$SOCK" send-keys "$@"; }
snap() {  # snap <name>: dump the pane for post-hoc scene review
  [ -n "$SNAP_DIR" ] || return 0
  mkdir -p "$SNAP_DIR"
  tmux -L "$SOCK" capture-pane -p > "$SNAP_DIR/$1.txt"
}

sleep 16                                   # first paint (fetches live markets)
snap 01_home
# Browse the trending list, peek two categories, return.
K Down; sleep 0.5; K Down; sleep 0.5; K Down; sleep 0.7
K Tab; sleep 1.8                           # -> Politics
K Tab; sleep 1.8                           # -> Sports
K BTab; sleep 1.0; K BTab; sleep 1.4       # back to Trending
snap 02_categories
# Star two events, then open the watchlist. Down-then-Up parks the cursor
# on the top row (the flagship market) without tripping TopReached.
K Down; sleep 0.5; K Up; sleep 0.5
K Space; sleep 0.8                         # star the top row
K Down; sleep 0.4; K Down; sleep 0.5
K Space; sleep 0.9                         # star another
snap 03_starred
K w; sleep 2.6                             # watchlist: just the starred rows
snap 04_watchlist
# Open the starred event, then its top market.
K Enter; sleep 3.2
snap 05_event
K Enter; sleep 4.0
snap 06_market
# Buy: b prefills the price from the touch and focuses size. Enter reviews,
# a second deliberate Enter places - DRY signs the order, never posts it.
K b; sleep 2.4
K 1 0; sleep 1.4
K Enter; sleep 2.4                         # review strip: cost, tick, warnings
snap 07_review
K Enter; sleep 2.8                         # DRY RUN: signed, not posted
snap 08_dry_placed
# The panel closes itself after placing; focus is back on the outcomes.
# Cursor down into the live book.
K Down; sleep 0.7; K Down; sleep 0.7; K Down; sleep 0.7; K Down; sleep 1.2
snap 09_book
# A public trader's book, read-only: expand the tape, open the top trader.
K a; sleep 2.0
K Right; sleep 4.5
snap 10_trader
K Escape; sleep 1.0; K Escape; sleep 1.2; K Escape; sleep 1.4
# Search, then out.
K /; sleep 1.0
K "bitcoin"; sleep 2.2
snap 11_search
K Escape; sleep 1.0
K q; sleep 2.0
tmux -L "$SOCK" kill-server 2>/dev/null || true

echo "Trimming dead time..."
python3 "$ROOT/scripts/trim_cast.py" "$RAW" "$TRIMMED"
echo "Redacting identity -> $OUT"
python3 "$ROOT/scripts/redact_cast.py" "$TRIMMED" "$OUT" \
  --funder "$FUNDER" ${NAME:+--name "$NAME"}
rm -rf "$RAW" "$TRIMMED" "$REC_HOME"
echo "Done: $OUT ($(wc -c < "$OUT") bytes)"
