"""The app's visual identity: a deep-navy theme and soft semantic colors.

Modeled on the landing-page mock (Byron, 2026-07-05): near-black navy
surfaces, one restrained blue accent, muted green/red for direction, and
prices in plain bold white. Widgets that colour by meaning import from
here instead of using terminal ANSI names, so the look does not depend on
the terminal's palette.
"""

from __future__ import annotations

from textual.theme import Theme

# Direction / P&L
UP = "#3fcf8e"
DOWN = "#f8717a"
# The single accent (bars, active tab, cursor tint)
BLUE = "#5b8ef7"
# Warnings / DRY badge
AMBER = "#e0af68"
# Chart furniture (fixed RGB, never terminal ANSI): the empty stretch of a
# probability bar and the inspect crosshair. Same values the widgets used as
# rich "grey30"/"grey58" - named here so every grey traces back to the theme.
TRACK = "#4e4e4e"
CROSSHAIR = "#949494"


def rgb(hex_color: str) -> tuple[int, int, int]:
    """Theme hex -> (r, g, b) for chart renderers that paint by component -
    charts derive from the constants above instead of hand-copied tuples."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

PMTUI_THEME = Theme(
    name="pmtui",
    primary=BLUE,
    secondary="#7aa2f7",
    accent=BLUE,
    foreground="#c9d4e3",
    background="#0a0e16",
    surface="#0d1320",
    panel="#131a2a",
    success=UP,
    warning=AMBER,
    error=DOWN,
    dark=True,
)
