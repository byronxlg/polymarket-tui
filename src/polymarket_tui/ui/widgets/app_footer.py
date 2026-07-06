"""Footer splitting Contextual keys from Global navigation.

Two hotkey vocabularies, rendered apart so they read at a glance:

- Contextual (left, default styling, lowercase labels): keys that act on
  the focused pane's selection - open, star, buy, sell, trades, rules...
  These change from screen to screen.
- Global (right-aligned past a divider, blue, Capitalized labels): keys
  that mean the same thing everywhere - Quit, Search, Portfolio, Watched,
  Back, Help, Refresh. A binding is Global when it lives on the App or
  when a pane binds a key straight to an app.* action.

The command-palette chip keeps Textual's stock right-docked treatment.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.dom import DOMNode
from textual.widgets import Footer, Static

# Private import, pinned dep: FooterKey is the stock chip renderer and has
# no public re-export; subclassing Footer already couples us to its shape.
from textual.widgets._footer import FooterKey


class AppFooter(Footer):
    # Screen-local actions that are app navigation in disguise (search's
    # esc pops the screen itself); app.* actions self-identify.
    _GLOBAL_ACTIONS = ("back_or_pop",)

    def _is_global(self, node: DOMNode, binding: Binding) -> bool:
        return (
            node is self.app
            or binding.action.startswith("app.")
            or binding.action in self._GLOBAL_ACTIONS
        )

    def compose(self) -> ComposeResult:
        if not self._bindings_ready:
            return
        active_bindings = self.screen.active_bindings
        contextual: list[tuple[Binding, bool, str]] = []
        global_keys: list[tuple[Binding, bool, str]] = []
        seen_actions: set[str] = set()
        for node, binding, enabled, tooltip in active_bindings.values():
            if not binding.show or binding.action in seen_actions:
                continue
            seen_actions.add(binding.action)
            bucket = global_keys if self._is_global(node, binding) else contextual
            bucket.append((binding, enabled, tooltip))
        for binding, enabled, tooltip in contextual:
            yield FooterKey(
                binding.key,
                self.app.get_key_display(binding),
                binding.description,
                binding.action,
                disabled=not enabled,
                tooltip=tooltip,
            ).data_bind(compact=Footer.compact)
        if global_keys:
            # 1fr spacer pushes the Global group to the right edge; its
            # border draws the divider between the two vocabularies.
            yield Static(id="footer-split")
        for binding, enabled, tooltip in global_keys:
            yield FooterKey(
                binding.key,
                self.app.get_key_display(binding),
                binding.description.capitalize(),
                binding.action,
                disabled=not enabled,
                tooltip=tooltip,
                classes="-global",
            ).data_bind(compact=Footer.compact)
        if self.show_command_palette and self.app.ENABLE_COMMAND_PALETTE:
            try:
                _node, binding, enabled, tooltip = active_bindings[
                    self.app.COMMAND_PALETTE_BINDING
                ]
            except KeyError:
                pass
            else:
                yield FooterKey(
                    binding.key,
                    self.app.get_key_display(binding),
                    binding.description,
                    binding.action,
                    classes="-command-palette",
                    disabled=not enabled,
                    tooltip=binding.tooltip or binding.description,
                )
