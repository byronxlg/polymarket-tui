#!/usr/bin/env bash
# Installs polymarket-tui as a uv tool:
#   curl -sSL https://raw.githubusercontent.com/byronxlg/polymarket-tui/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/byronxlg/polymarket-tui"

say() { printf '%s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || fail "git is required (uv installs from the git repo)"

if ! command -v uv >/dev/null 2>&1; then
  say "uv not found - installing it from https://astral.sh/uv ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv installation failed - install it manually, then re-run this script"
fi

say "Installing polymarket-tui from $REPO ..."
uv tool install --force "git+$REPO"

if command -v polymarket-tui >/dev/null 2>&1; then
  say "Installed. Run: polymarket-tui"
else
  say "Installed, but the uv tool bin directory is not on your PATH."
  say "Run 'uv tool update-shell', open a new shell, then run: polymarket-tui"
fi
