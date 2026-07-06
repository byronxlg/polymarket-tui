# Homebrew distribution

Goal: a bare `brew install polymarket-tui` (no tap prefix), which means getting
the formula accepted into **homebrew-core**. The name `polymarket-tui` is free
in core and on PyPI (checked 2026-07-06).

Until then, the **personal tap** (`Formula/polymarket-tui.rb`) is the working
channel and needs no approval - see [Interim: install today](#interim-install-today).

## Acceptance gates

Homebrew-core is not a namespace you can just push to; a maintainer reviews a PR
into `Homebrew/homebrew-core`. Three gates stand between us and merge:

| Gate | Status | Blocker |
|------|--------|---------|
| 1. Notability | BLOCKED | 0 stars / 0 forks / 0 watchers. Organic only - not a code change. |
| 2. Open-source license | DONE | MIT `LICENSE` + `license = "MIT"` in `pyproject.toml`. |
| 3. Stable versioned source + vendored resources | READY (needs a publish) | Formula drafted; needs a published sdist to pin `url`/`sha256`. |

### Gate 1 - Notability (the real blocker)

Homebrew-core rejects software that is not "notable and maintained." The rough
historical bar is on the order of 30+ forks / 30+ watchers / 75+ stars, or
equivalent evidence the project is widely used. `brew audit --new` queries the
GitHub API and maintainers reject on sight if it looks like a personal repo.

At 0 stars this WILL be rejected. Nothing in this repo changes that - it needs
real adoption first. Practical read: ship via the tap (and PyPI) now, let usage
accrue, and open the core PR once the numbers are defensible. Everything else
below is done so that submission is a 10-minute task when that day comes.

### Gate 2 - License (done)

Core requires an OSI license. Added:

- `LICENSE` (MIT, top level)
- `license = "MIT"` + `license-files = ["LICENSE"]` in `pyproject.toml`
  (PEP 639; `uv build` emits `License-Expression: MIT`)
- `license "MIT"` in the formula

### Gate 3 - Stable source + vendored resources

Core builds Python apps from a **published sdist** into a virtualenv, with every
runtime dependency vendored as a pinned `resource` block. It does NOT allow
`pip install` at build time (the current tap formula does that - fine for a tap,
not for core). The submission formula is drafted at
[`packaging/homebrew-core/polymarket-tui.rb`](../packaging/homebrew-core/polymarket-tui.rb):

- `include Language::Python::Virtualenv` + `virtualenv_install_with_resources`
- `depends_on "python@3.12"`
- 56 `resource` blocks - the full runtime closure, generated from `uv.lock`
- a real test: `polymarket-tui --version` (added a lightweight argparse
  `--version`/`--help` to `__main__.py` so the binary is inspectable headlessly)

Two placeholders remain, both filled only after a release exists: the main
package `url` and its `sha256`.

#### Steps to make it submittable

1. **Tag a release** and **publish the sdist to PyPI** (name is free):
   ```sh
   uv build --sdist
   uv publish            # needs a PyPI token; also enables `pip install polymarket-tui`
   git tag v0.1.0 && git push --tags
   ```
2. **Fill `url` + `sha256`** in the formula from PyPI:
   ```sh
   curl -s https://pypi.org/pypi/polymarket-tui/0.1.0/json \
     | jq -r '.urls[] | select(.packagetype=="sdist") | .url, .digests.sha256'
   ```
   Replace the `packages/source/p/...` placeholder url with the returned hashed
   path (the `FormulaAudit/PyPiUrls` style warning goes away once you do).
3. **Regenerate resources** if any dependency changed since this draft:
   ```sh
   uv run python scripts/gen_brew_resources.py > /tmp/resources.rb
   # splice between the depends_on line and `def install`
   ```
   or use Homebrew's own resolver once the formula is in a tap:
   `brew update-python-resources packaging/homebrew-core/polymarket-tui.rb`.
4. **Audit + build locally** (this is what the reviewer runs):
   ```sh
   brew install --build-from-source packaging/homebrew-core/polymarket-tui.rb
   brew test packaging/homebrew-core/polymarket-tui.rb
   brew audit --new --strict --online polymarket-tui
   ```
5. **Open the PR**: `brew bump-formula-pr` / a manual PR that adds
   `Formula/p/polymarket-tui.rb` to `Homebrew/homebrew-core`.

## Note: upstream drags pytest into runtime

`poly-eip712-structs` and `py-order-utils` (Polymarket's own libs, pulled in via
`py-clob-client`) declare `pytest` as a **runtime** `install_requires`. So the
runtime closure - and therefore any `pip install` and this formula - includes
`pytest`, `pluggy`, and `iniconfig`. This is an upstream packaging wart we can't
fix here; `brew update-python-resources` would include them too. Harmless, just
noted so the extra resources don't look like a mistake.

## Regenerating the resource list

`scripts/gen_brew_resources.py` reads `uv.lock` (single source of truth for
pinned versions + hashes), walks the runtime-only closure from the root's
`[project.dependencies]` (handling the `httpx[http2]` extra), excludes dev tools,
and emits sorted `resource` blocks. Every dependency has an sdist, so all 56
build from source.

```sh
uv run python scripts/gen_brew_resources.py --report   # blocks + included/excluded
```

Re-run after any dependency bump and re-splice into the formula.

## Interim: install today

No approval needed - these work now:

- **Tap** (`Formula/polymarket-tui.rb`, repo doubles as the tap):
  ```sh
  brew tap byronxlg/polymarket-tui https://github.com/byronxlg/polymarket-tui
  brew install polymarket-tui
  ```
- **uv tool** (one-liner in `install.sh`): installs from git.
- **PyPI** (once `uv publish` is run): `uv tool install polymarket-tui` or
  `pipx install polymarket-tui`.
