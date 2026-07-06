# Changelog

All notable changes to polymarket-tui are documented here. This project follows
[semantic versioning](https://semver.org/).

## [0.1.1] - 2026-07-07

### Fixed
- `CursorFollow`: the first cursor-follow is no longer suppressed on
  freshly-booted hosts (a `monotonic()`-from-boot edge case).

### Changed
- README now leads with an animated demo and PyPI/Python/license badges.
- PyPI page is discoverable: search keywords, trove classifiers, and sidebar
  links (Homepage, Repository, Issues, Changelog).

## [0.1.0] - 2026-07-06

Initial release, published to PyPI and installable via Homebrew
(`brew install byronxlg/tap/polymarket-tui`).

- Browse markets and events with live previews, categories, and search.
- Live order books and trade tape over WebSocket (REST snapshot fallback).
- Price charts across timeframes.
- Portfolio: positions, P&L, and activity for any funder address.
- Trader profiles and follow.
- Order placement, fully validated and signed, dry-run by default; LIVE is an
  explicit, confirmed opt-in. Every order/cancel is audited to a local JSONL.
- `--version` / `--help` on the CLI.
