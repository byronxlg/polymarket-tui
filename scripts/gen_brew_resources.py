#!/usr/bin/env python3
"""Generate Homebrew `resource` blocks for the runtime dependency closure.

Homebrew-core Python formulae vendor every runtime dependency as a `resource`
block (name + sdist url + sha256) and install them into a virtualenv. This
reads uv.lock (the single source of truth for pinned versions and hashes) and
emits those blocks, sorted, for the runtime-only closure - dev tools (pytest,
ruff, ...) are excluded.

    uv run python scripts/gen_brew_resources.py           # print blocks
    uv run python scripts/gen_brew_resources.py --report  # + included/excluded

The output is pasted between the RESOURCES markers in
Formula/polymarket-tui-core.rb. Regenerate after any dependency bump.
"""
from __future__ import annotations

import argparse
import sys
import tomllib

ROOT = "polymarket-tui"


def load_lock(path: str = "uv.lock") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def index(lock: dict) -> dict[str, dict]:
    return {p["name"]: p for p in lock["package"]}


def runtime_closure(pkgs: dict[str, dict]) -> set[str]:
    """BFS from the root's runtime deps, following each package's dependencies
    and any requested extras (optional-dependencies)."""
    root = pkgs[ROOT]
    # (name, frozenset-of-extras) queue; extras drive optional-dependencies.
    queue: list[tuple[str, frozenset[str]]] = []
    for dep in root.get("dependencies", []):
        queue.append((dep["name"], frozenset(dep.get("extra", []))))
    seen: set[str] = set()
    visited_state: set[tuple[str, frozenset[str]]] = set()
    while queue:
        name, extras = queue.pop()
        state = (name, extras)
        if state in visited_state:
            continue
        visited_state.add(state)
        seen.add(name)
        pkg = pkgs.get(name)
        if not pkg:
            continue
        deps = list(pkg.get("dependencies", []))
        opt = pkg.get("optional-dependencies", {})
        for ex in extras:
            deps.extend(opt.get(ex, []))
        for dep in deps:
            queue.append((dep["name"], frozenset(dep.get("extra", []))))
    seen.discard(ROOT)
    return seen


def resource_block(pkg: dict) -> str:
    sdist = pkg["sdist"]
    return (
        f'  resource "{pkg["name"]}" do\n'
        f'    url "{sdist["url"]}"\n'
        f'    sha256 "{sdist["hash"].removeprefix("sha256:")}"\n'
        f"  end\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--lock", default="uv.lock")
    args = ap.parse_args()

    lock = load_lock(args.lock)
    pkgs = index(lock)
    runtime = runtime_closure(pkgs)

    missing_sdist = sorted(n for n in runtime if "sdist" not in pkgs[n])
    if missing_sdist:
        print(
            "ERROR: runtime deps without an sdist (Homebrew builds from source):\n  "
            + "\n  ".join(missing_sdist),
            file=sys.stderr,
        )
        return 1

    if args.report:
        all_deps = set(pkgs) - {ROOT}
        excluded = sorted(all_deps - runtime)
        print(f"# runtime resources: {len(runtime)}", file=sys.stderr)
        print(f"# excluded (dev-only): {len(excluded)}", file=sys.stderr)
        for n in excluded:
            print(f"#   - {n}", file=sys.stderr)

    # Blank line between blocks: Homebrew's `brew style` requires it.
    print("\n".join(resource_block(pkgs[name]) for name in sorted(runtime)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
