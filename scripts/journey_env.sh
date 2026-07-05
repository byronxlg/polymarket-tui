#!/bin/sh
# Prepare an isolated HOME for journey runs (docs/user-journeys.md).
# Prints the HOME path. Never points at the real $HOME: the real creds file
# persists the LIVE flag, and automated keys must never place real orders.
#   anon       - signed out, browse-only
#   authed-dry - real creds copied with execution_live forced to false
set -eu
mode="${1:?usage: journey_env.sh <anon|authed-dry>}"
base="${TMPDIR:-/tmp}/pmtui-journey-home-$mode"
mkdir -p "$base"
case "$mode" in
anon)
    # Fresh casual every run: no creds and no watchlist/audit state left
    # over from an earlier journey.
    rm -rf "$base/.config/polymarket-tui" "$base/.local/share/polymarket-tui"
    ;;
authed-dry)
    src="$HOME/.config/polymarket-tui/credentials.toml"
    [ -f "$src" ] || { echo "no credentials at $src" >&2; exit 1; }
    mkdir -p "$base/.config/polymarket-tui"
    sed 's/^execution_live[[:space:]]*=.*/execution_live = false/' "$src" \
        >"$base/.config/polymarket-tui/credentials.toml"
    chmod 600 "$base/.config/polymarket-tui/credentials.toml"
    grep -q '^execution_live = false$' "$base/.config/polymarket-tui/credentials.toml" || {
        echo "failed to force execution_live=false" >&2
        exit 1
    }
    ;;
*)
    echo "unknown mode: $mode" >&2
    exit 1
    ;;
esac
printf '%s\n' "$base"
