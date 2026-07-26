#!/usr/bin/env bash
# Record a vertical short: drive the real TUI through a beat sheet and capture
# it as an asciinema cast plus the beat timings the renderer needs.
#
#   record.sh <beats.json> <outdir>
#
# Writes <outdir>/<slug>.cast and <outdir>/<slug>.timings.json.
#
# Geometry is 120x38, not a phone-shaped terminal. Below ~100 columns the
# market screen falls apart: the order book collapses to a vertical "OR/DE/R"
# label strip with no rows, the YES/NO chips crush to "Y"/"N", and the outcome
# rail clips prices mid-number ("100", "99."). So the app is never recorded at
# phone aspect - render.py composites this native-aspect capture into a
# 1080x1920 frame instead.
#
# Runs authed in DRY under an isolated HOME (journey_env.sh authed-dry, which
# forces execution_live=false) with POLYMARKET_HIDE_BALANCES=1, then redacts
# identity through redact_cast.py exactly like record_demo.sh. A short can
# never place an order and can never ship Byron's balances or profile name.
#
# Requires: asciinema, tmux, agg, ffmpeg, jq, real credentials.
set -euo pipefail

BEATS="${1:?usage: record.sh <beats.json> <outdir>}"
OUTDIR="${2:?usage: record.sh <beats.json> <outdir>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

COLS=120
ROWS=38
# Unique per invocation: `-L pmtui` is shared, and a parallel job's session
# would otherwise receive these keystrokes (or have its pane captured).
SOCK="pmtui-short-$$"
SESS="short"
APP="$ROOT/.venv/bin/python -u -m polymarket_tui"

command -v asciinema >/dev/null || { echo "asciinema not found: uv tool install asciinema" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }

SLUG="$(jq -r '.slug' "$BEATS")"
mkdir -p "$OUTDIR"
RAW="$(mktemp -t pmtui-short-XXXX).cast"
CAST="$OUTDIR/$SLUG.cast"
TIMINGS="$OUTDIR/$SLUG.timings.json"

REC_HOME="$("$ROOT/scripts/journey_env.sh" authed-dry)"
FUNDER="$(python3 -c "
import tomllib
print(tomllib.load(open('$REC_HOME/.config/polymarket-tui/credentials.toml','rb'))['funder'])")"
NAME="$(curl -sf -A Mozilla/5.0 "https://gamma-api.polymarket.com/public-profile?address=$FUNDER" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('name') or d.get('pseudonym') or '')" \
  || true)"

K() { tmux -L "$SOCK" send-keys -t "$SESS" "$@"; }
cleanup() { tmux -L "$SOCK" kill-server 2>/dev/null || true; }
trap cleanup EXIT

wait_for_rows() { # block until the trending list has market rows (a $ volume)
    for _ in $(seq 1 80); do
        tmux -L "$SOCK" capture-pane -p -t "$SESS" 2>/dev/null | grep -qE '\$[0-9]' && return 0
        sleep 0.3
    done
    echo "timed out waiting for market rows" >&2
    return 1
}

# The landing-page demo warms the events cache first so its boot paints
# instantly. A short must not: a warmed cache makes home open under the amber
# "cached list from your last session / refreshing..." banner, which is the
# first thing a viewer reads. render.py trims the whole boot anyway, so the
# warm-up buys nothing here and costs the opening frame. Start cold.
rm -rf "$REC_HOME/.local/share/polymarket-tui/cache"
cleanup

echo "Recording ${COLS}x${ROWS} (authed DRY, balances hidden) -> $RAW"
REC_START="$(python3 -c 'import time; print(time.time())')"
tmux -L "$SOCK" new-session -d -s "$SESS" -x "$COLS" -y "$ROWS" \
    -e HOME="$REC_HOME" -e POLYMARKET_HIDE_BALANCES=1 \
    "asciinema rec '$RAW' --overwrite -q -c '$APP'"

wait_for_rows
# Rows painting is not the same as the app being settled. On a cold start the
# category bar and sort line land after the table, leaving a blank band where
# the tabs belong; the header also reads "loading account" for a beat. Both are
# honest and both look like a broken app in the opening frame, so require a
# fully painted home before the first beat: tabs present, nothing still loading.
for _ in $(seq 1 80); do
    pane="$(tmux -L "$SOCK" capture-pane -p -t "$SESS" 2>/dev/null || true)"
    if printf '%s' "$pane" | grep -q 'Trending' &&
        printf '%s' "$pane" | grep -q 'cycle sort' &&
        ! printf '%s' "$pane" | grep -qE 'loading account|refreshing'; then
        break
    fi
    sleep 0.25
done
sleep 0.6 # let the first live refresh settle so prices are not mid-repaint
# Everything downstream is timed from this instant. head_offset tells render.py
# where to cut, so the trim anchor and the beat clock share one origin: anchor
# the cut on "first frame with a price" instead and it lands mid-boot, before
# the tabs paint, while the captions still count from here - which desyncs
# every caption and opens on a half-drawn screen.
# The offset is measured against the wall clock just before asciinema started,
# so it runs slightly long by however much tmux and asciinema took to boot.
# That errs toward cutting a fraction of settled footage, never toward showing
# an unsettled frame.
T0="$(python3 -c 'import time; print(time.time())')"
HEAD_OFFSET="$(python3 -c "print(round($T0 - $REC_START, 3))")"
echo "head_offset ${HEAD_OFFSET}s"
elapsed() { python3 -c "import time; print(round(time.time() - $T0, 3))"; }

NBEATS="$(jq '.beats | length' "$BEATS")"
echo "Driving $NBEATS beats..."
echo "[]" >"$TIMINGS.tmp"
for i in $(seq 0 $((NBEATS - 1))); do
    at="$(elapsed)"
    caption="$(jq -r ".beats[$i].caption // \"\"" "$BEATS")"
    typed="$(jq -r ".beats[$i].type // \"\"" "$BEATS")"
    wait_s="$(jq -r ".beats[$i].wait // 2" "$BEATS")"

    [ -n "$typed" ] && { K -l "$typed"; sleep 0.4; }
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        K "$key"
        sleep 0.35
    done < <(jq -r ".beats[$i].keys // [] | .[]" "$BEATS")
    sleep "$wait_s"

    jq --argjson at "$at" --arg cap "$caption" --argjson until "$(elapsed)" \
        '. + [{at: $at, until: $until, caption: $cap}]' \
        "$TIMINGS.tmp" >"$TIMINGS.tmp2" && mv "$TIMINGS.tmp2" "$TIMINGS.tmp"
done
jq --argjson head "$HEAD_OFFSET" '{head_offset: $head, beats: .}' \
    "$TIMINGS.tmp" >"$TIMINGS"
rm -f "$TIMINGS.tmp"

K q
sleep 1.5
cleanup

echo "Redacting identity -> $CAST"
python3 "$ROOT/scripts/redact_cast.py" "$RAW" "$CAST" \
    --funder "$FUNDER" ${NAME:+--name "$NAME"}
rm -f "$RAW"
rm -rf "$REC_HOME"
echo "Done: $CAST ($(wc -c <"$CAST") bytes), $TIMINGS"
