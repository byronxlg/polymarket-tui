"""Every keybinding in the app must be documented in the help screen.

The help text drifted from the code once already (O, t, m, ctrl+s, ctrl+d and
the `<` back alias were all bound but undocumented). This test walks every
BINDINGS list under polymarket_tui.ui and asserts each key appears as a table
cell in HELP_TEXT, so a new binding cannot ship without a help row.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

from textual.binding import Binding

import polymarket_tui.ui as ui_pkg
from polymarket_tui.ui.screens.help import HELP_TEXT

# Movement/confirmation keys. The help's "core keys" table describes these as a
# vocabulary ("arrows", "right or enter", "left or escape") rather than listing
# every variant, so they are exempt from the per-key table-cell requirement.
CORE_KEYS = frozenset(
    {
        "up",
        "down",
        "left",
        "right",
        "shift+up",
        "shift+down",
        "shift+left",
        "shift+right",
        "enter",
        "escape",
        "tab",
        "shift+tab",
        "space",
        "home",
    }
)

# Textual spells punctuation keys out; the help shows the glyph.
KEY_GLYPHS = {
    "question_mark": "?",
    "slash": "/",
    "less_than_sign": "<",
    "comma": ",",
}


def _iter_binding_classes():
    """Every class under polymarket_tui.ui that declares its own BINDINGS."""
    for mod_info in pkgutil.walk_packages(ui_pkg.__path__, f"{ui_pkg.__name__}."):
        module = importlib.import_module(mod_info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue  # imported, not defined here - avoid double-counting
            if "BINDINGS" in vars(obj):
                yield obj


def _binding_keys(cls) -> list[tuple[str, str]]:
    """(key, action) for each binding declared on cls, one row per key."""
    out: list[tuple[str, str]] = []
    for entry in vars(cls)["BINDINGS"]:
        if isinstance(entry, Binding):
            key, action = entry.key, entry.action
        else:  # tuple form: (key, action, description)
            key, action = entry[0], entry[1]
        for part in str(key).split(","):
            part = part.strip()
            if part:
                out.append((KEY_GLYPHS.get(part, part), action))
    return out


def _documented_keys() -> set[str]:
    """Tokens in the first column of every markdown table row in HELP_TEXT."""
    documented: set[str] = set()
    for line in HELP_TEXT.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cell = line.strip("|").split("|")[0].strip()
        if not cell or set(cell) <= {"-", ":"} or cell.lower() == "key":
            continue  # separator row or header
        # Backticks quote a key that would otherwise look like a separator -
        # the sort key is a literal comma, so the help writes it as `,`.
        if literals := re.findall(r"`([^`]+)`", cell):
            documented.update(t.strip() for t in literals if t.strip())
            continue
        # " / " and " or " separate alternatives; a bare "/" is the search key,
        # so the slash separator requires surrounding whitespace.
        for token in re.split(r"\s+or\s+|\s+/\s+|\s*,\s*", cell):
            token = token.strip()
            if token:
                documented.add(token)
    return documented


def test_help_documents_every_binding() -> None:
    documented = _documented_keys()
    missing: set[str] = set()
    where: dict[str, set[str]] = {}

    for cls in _iter_binding_classes():
        for key, action in _binding_keys(cls):
            if key in CORE_KEYS or key in documented:
                continue
            missing.add(key)
            where.setdefault(key, set()).add(f"{cls.__name__}.{action}")

    assert not missing, "keys bound but absent from the help tables: " + ", ".join(
        f"{k} ({', '.join(sorted(where[k]))})" for k in sorted(missing)
    )


def test_help_tables_document_no_phantom_keys() -> None:
    """The reverse guard: every key in a help table is actually bound somewhere."""
    bound = {key for cls in _iter_binding_classes() for key, _ in _binding_keys(cls)}
    bound |= CORE_KEYS
    # Named keys the help refers to that Textual spells differently.
    bound |= {"Home", "arrows"}

    phantom = {k for k in _documented_keys() if k not in bound}
    assert not phantom, f"help documents unbound keys: {sorted(phantom)}"
