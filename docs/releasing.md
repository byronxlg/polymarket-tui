# Releasing

Publishing is done by GitHub Actions on a published release - never `uv publish`
from a laptop. Cutting a GitHub release triggers
[`.github/workflows/publish.yml`](../.github/workflows/publish.yml), which tests,
builds, and uploads to PyPI. The version shipped is whatever is in
`pyproject.toml` at the tagged commit.

Channels: **PyPI** only (npm was considered and skipped - a Python TUI on npm
needs a Node shim that bootstraps Python, with no benefit over PyPI + Homebrew +
the uv one-liner). A PyPI release also unlocks `pip install polymarket-tui`,
`uv tool install polymarket-tui`, and gives the homebrew-core formula a stable
sdist to source from (see [homebrew-core.md](homebrew-core.md)).

## One-time: PyPI Trusted Publishing (no token stored)

We use OIDC Trusted Publishing, so no PyPI token lives in GitHub secrets. Because
the project does not exist on PyPI yet, register a **pending** publisher first:

1. Log in to PyPI -> https://pypi.org/manage/account/publishing/
2. Add a **pending publisher** with exactly:
   - PyPI Project Name: `polymarket-tui`
   - Owner: `byronxlg`
   - Repository name: `polymarket-tui`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. In GitHub -> repo Settings -> Environments, create an environment named
   `pypi` (optionally add release protection / required reviewers).

The first successful release run claims the PyPI project and converts the
pending publisher into an active one.

## Cutting a release

1. Bump `version` in `pyproject.toml` (semver).
2. Commit on `main`, then tag and create the release:
   ```sh
   VERSION=0.1.0
   git tag "v$VERSION" && git push origin "v$VERSION"
   gh release create "v$VERSION" --generate-notes
   ```
   (or use the GitHub UI - "Publish release" is what fires the workflow).
3. Watch it: `gh run watch` / the Actions tab. On success the version is live at
   https://pypi.org/project/polymarket-tui/.

`workflow_dispatch` is also enabled for a manual re-run if a release publish
needs to be retried (PyPI rejects re-uploading an existing version, so bump
first).

## After the first PyPI release

- Update the homebrew-core formula's `url`/`sha256` from PyPI - see
  [homebrew-core.md](homebrew-core.md) step 2.
- `pip install polymarket-tui` / `uv tool install polymarket-tui` now work.
