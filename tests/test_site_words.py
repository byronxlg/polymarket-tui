"""The landing page may only show words from docs/ux/words.md.

Three rules, so wording never needs reviewing by hand (docs/ux/words.md):
a page shows only words from the Word column; the page stays inside its word
budget; the word list cannot change without a recorded cold read.
"""
from __future__ import annotations

import hashlib
import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORDS = ROOT / "docs" / "ux" / "words.md"
COLD_READS = ROOT / "docs" / "ux" / "cold-reads.md"
BUDGET = 220
# Pages built on the new design. site/index.html joins when the preview is promoted.
CANDIDATES = (ROOT / "site" / "next" / "index.html", ROOT / "site" / "index.html")
PAGES = [p for p in CANDIDATES if p.exists() and "assets/site.css" in p.read_text()]
SKIP = {"script", "style", "pre", "code", "kbd"}
SPOKEN = {"alt", "aria-label", "title"}
TOKEN = re.compile(r"[A-Za-z][A-Za-z.'-]*[A-Za-z]|[A-Za-z]")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.text: list[str] = []
        self.spoken: list[str] = []
        self.version = ""
        self.commands: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag not in {"meta", "link", "img", "source", "br"}:
            self.stack.append(tag)
        for k in SPOKEN & a.keys():
            self.spoken.append(a[k] or "")
        if tag == "meta" and a.get("name") == "description":
            self.spoken.append(a.get("content") or "")

    def handle_endtag(self, tag: str) -> None:
        while self.stack and self.stack.pop() != tag:
            pass

    def handle_data(self, data: str) -> None:
        if "title" in self.stack:
            self.spoken.append(data.strip())
        elif "pre" in self.stack:
            self.commands.append(data)
        elif not SKIP & set(self.stack):
            m = re.fullmatch(r"v(\d+\.\d+\.\d+)", data.strip())
            if m:
                self.version = m.group(1)
            else:
                self.text.append(data)


def parse(path: Path) -> Page:
    page = Page()
    page.feed(path.read_text())
    return page


def allowed_words() -> set[str]:
    rows = [r for r in WORDS.read_text().splitlines() if r.startswith("| ") and "---" not in r]
    cells = [row.split("|")[2] for row in rows[1:]]
    return {w.lower() for cell in cells for w in TOKEN.findall(cell)}


def visible_words(page: Page) -> list[str]:
    return [w for chunk in page.text for w in re.findall(r"[^\s·]+", chunk) if re.search(r"\w", w)]


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
class TestPage:
    def test_only_words_from_the_list(self, path: Path) -> None:
        allowed = allowed_words()
        shown = {w for chunk in parse(path).text for w in TOKEN.findall(chunk)}
        strangers = sorted(w for w in shown if w.lower() not in allowed)
        assert not strangers, f"not in docs/ux/words.md: {strangers}"

    def test_word_budget(self, path: Path) -> None:
        n = len(visible_words(parse(path)))
        assert n <= BUDGET, f"{n} visible words, budget {BUDGET}"

    def test_spoken_strings_are_listed(self, path: Path) -> None:
        listed = WORDS.read_text()
        missing = [s for s in parse(path).spoken if s and s not in listed]
        assert not missing, f"not listed verbatim in docs/ux/words.md: {missing}"

    def test_version_matches_the_package(self, path: Path) -> None:
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
        assert parse(path).version == version

    def test_commands_match_the_readme(self, path: Path) -> None:
        readme = (ROOT / "README.md").read_text() + (ROOT / "install.sh").read_text()
        for block in set(parse(path).commands):
            for line in block.splitlines():
                for part in line.split(" && "):
                    assert part.strip() in readme, f"command not in README: {part!r}"


def test_pages_found() -> None:
    assert PAGES


def test_word_list_has_a_cold_read() -> None:
    digest = hashlib.sha256(WORDS.read_bytes()).hexdigest()[:16]
    recorded = re.findall(r"^\| \S+ \| ([0-9a-f]{16}) \|", COLD_READS.read_text(), flags=re.M)
    assert recorded and recorded[-1] == digest, (
        f"docs/ux/words.md changed (now {digest}); "
        "run a cold read and record it in docs/ux/cold-reads.md"
    )
