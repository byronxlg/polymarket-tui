"""Width tiers for drill panes hosted by NavHost.

Every drill pane renders at one of three tiers set on each NavHost reflow:

- "compact": the 30% parent slot - the pane is context, only its primary
  list survives.
- "medium": the 70% child slot - the main content with slimmed rails.
- "full": the pane has the whole window (root with nothing drilled).

NavHost stamps a tier-<name> CSS class per reflow so app.tcss can show/hide
rails declaratively, and calls set_tier() so panes can rebuild what CSS
cannot reach (DataTable column sets).
"""

from __future__ import annotations

from typing import Literal

Tier = Literal["compact", "medium", "full"]
TIERS: tuple[Tier, ...] = ("compact", "medium", "full")
TIER_ORDER: dict[Tier, int] = {"compact": 0, "medium": 1, "full": 2}

# (key, label, width) - one table column.
ColumnSpec = tuple[str, str, int]


def columns_need(columns: tuple[ColumnSpec, ...] | list[ColumnSpec]) -> int:
    """Cells render with one cell of padding each side."""
    return sum(width for _, _, width in columns) + 2 * len(columns)


def effective_tier(
    cap: Tier, width: int, tier_columns: dict[Tier, tuple[ColumnSpec, ...]]
) -> Tier:
    """Widest column set that the slot tier allows AND the measured width fits.

    The slot tier (compact/medium/full from NavHost) is a cap, not the
    answer: a 70% pane of a small terminal can be narrower than a 30% pane
    of a wide one, so the column set must follow real columns-on-screen.
    """
    for tier in ("full", "medium"):
        if TIER_ORDER[tier] <= TIER_ORDER[cap] and width >= columns_need(tier_columns[tier]):
            return tier  # type: ignore[return-value]
    return "compact"


def fit_columns(
    columns: tuple[ColumnSpec, ...] | list[ColumnSpec],
    width: int,
    flex_key: str,
    flex_max: int | None = None,
) -> list[ColumnSpec]:
    """Fit the set to `width` by resizing the primary text column.

    Deficit shrinks it (floor 14). Surplus grows it - but only up to
    flex_max (the longest actual cell content), so titles stop truncating
    as soon as there is room without pushing the numeric columns into the
    void when rows are short.
    """
    delta = width - columns_need(columns)
    if delta < 0:
        return [
            (key, label, max(14, w + delta) if key == flex_key else w)
            for key, label, w in columns
        ]
    if delta > 0 and flex_max is not None:
        return [
            (key, label, max(w, min(flex_max, w + delta)) if key == flex_key else w)
            for key, label, w in columns
        ]
    return list(columns)


class TierAware:
    """Mixin for drill panes: tracks the pane's current width tier.

    set_tier() can fire before the pane composes (NavHost reflows in the
    same tick it mounts a new pane), so it only records the tier until the
    pane declares itself ready. Panes build their tables from self.tier in
    on_mount, then call tier_ready(); later changes invoke on_tier_changed().
    """

    _tier: Tier = "full"
    _tier_ready: bool = False

    @property
    def tier(self) -> Tier:
        return self._tier

    def set_tier(self, tier: Tier) -> None:
        if tier == self._tier:
            return
        self._tier = tier
        if self._tier_ready:
            self.on_tier_changed(tier)

    def tier_ready(self) -> None:
        """Call at the end of on_mount, once tables are built from self.tier."""
        self._tier_ready = True

    def on_tier_changed(self, tier: Tier) -> None:
        """Rebuild whatever CSS can't restyle (table columns). Override."""
