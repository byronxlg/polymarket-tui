#!/usr/bin/env bash
# Record the landing-page demo cast (asciinema) of the TUI.
#
# Produces site/assets/demo.cast - a scripted tour, best features first:
# straight into the top market -> cursor the streaming book -> a BUY reviewed
# and placed in DRY -> flip to the NO book -> chart timeframe -> the trade
# tape and a public trader -> search. Runs authed in DRY under an isolated HOME
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

K() { tmux -L "$SOCK" send-keys "$@"; }
wait_for_rows() {  # block until the trending list has market rows (a $ volume)
  for _ in $(seq 1 60); do
    tmux -L "$SOCK" capture-pane -p 2>/dev/null | grep -qE '\$[0-9]' && return 0
    sleep 0.3
  done
  echo "timed out waiting for market rows" >&2
  return 1
}

# Warm the events cache with a throwaway run: the recorded boot then paints
# last-run's list instantly instead of an empty shell waiting on Gamma.
echo "Warming the events cache in $REC_HOME..."
tmux -L "$SOCK" kill-server 2>/dev/null || true
tmux -L "$SOCK" new-session -d -x "$COLS" -y "$ROWS" -e HOME="$REC_HOME" "$APP"
wait_for_rows
K q; sleep 1
tmux -L "$SOCK" kill-server 2>/dev/null || true

echo "Recording to $RAW (home=$REC_HOME, ${COLS}x${ROWS}, authed DRY, balances hidden)..."
tmux -L "$SOCK" new-session -d -x "$COLS" -y "$ROWS" \
  -e HOME="$REC_HOME" -e POLYMARKET_HIDE_BALANCES=1 \
  "asciinema rec '$RAW' --overwrite -q -c '$APP'"
snap() {  # snap <name>: dump the pane for post-hoc scene review
  [ -n "$SNAP_DIR" ] || return 0
  mkdir -p "$SNAP_DIR"
  tmux -L "$SOCK" capture-pane -p > "$SNAP_DIR/$1.txt"
}

wait_for_rows                              # cached list paints ~instantly
sleep 2.4                                  # live refresh lands; a beat to read
snap 01_home
# Straight to the good part: open the top trending event and its top market.
# Down-then-Up parks the cursor on the top row without tripping TopReached.
K Down; sleep 0.5; K Up; sleep 0.6
K Enter; sleep 2.8
snap 02_event
K Enter; sleep 3.8                         # market: book-first focus, live ws
snap 03_market
# Cursor down the streaming book - depth bars, mid, spread.
K Down; sleep 0.55; K Down; sleep 0.55; K Down; sleep 0.55; K Down; sleep 1.1
snap 04_book_cursor
# Buy: b prefills the price from the touch and focuses size. Enter reviews,
# a second deliberate Enter places - DRY signs the order, never posts it.
K b; sleep 1.8
K 1 0 0; sleep 1.3
K Enter; sleep 2.8                         # review strip: cost, payout, DRY
snap 05_review
K Enter; sleep 2.6                         # DRY RUN: signed, not posted
snap 06_dry_placed
# Flip the book to the NO side and back (tab is the outcome toggle).
K Tab; sleep 2.0
snap 07_no_book
K Tab; sleep 1.3
# Chart timeframe (t cycles it); one beat for the redraw.
K t; sleep 2.0
snap 08_chart
# The trade tape, then a public trader's profile - all read-only.
K a; sleep 2.0                             # expand the tape: sizes, USDC, names
snap 09_tape
K Down; sleep 0.8; K Down; sleep 0.9       # trader previews follow the cursor
K Right; sleep 4.2
snap 10_trader
K Escape; sleep 1.0; K Escape; sleep 1.2
# Search, then out.
K /; sleep 1.0
K "bitcoin"; sleep 2.4
snap 11_search
K Escape; sleep 0.9
K q; sleep 2.0
tmux -L "$SOCK" kill-server 2>/dev/null || true

echo "Trimming dead time..."
python3 "$ROOT/scripts/trim_cast.py" "$RAW" "$TRIMMED"
echo "Redacting identity -> $OUT"
python3 "$ROOT/scripts/redact_cast.py" "$TRIMMED" "$OUT" \
  --funder "$FUNDER" ${NAME:+--name "$NAME"}
rm -rf "$RAW" "$TRIMMED" "$REC_HOME"
echo "Done: $OUT ($(wc -c < "$OUT") bytes)"
