"""Search bar widget: live, debounced filtering with a regex toggle."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.widgets import Input

if TYPE_CHECKING:
    from textual.events import Key

    from ambrosia.tui.app import AmbrosiaApp


class SearchBar(Input):
    """The search input.

    The search bar is an :class:`~textual.widgets.Input` so that it owns its
    focus and its ``Input.Changed`` message (which bubbles up to the
    application for debounced filtering). It toggles regex mode with ``r``
    without inserting the character, and moves focus to the results on
    ``Tab``/``Enter``.
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(
            id=id,
            placeholder="type to filter commands ...  [regex: off]",
        )

    def focus_input(self) -> None:
        """Focus the search input (this widget is the input)."""
        self.focus()

    def set_regex_mode(self, on: bool) -> None:
        """Update the regex flag and the input placeholder hint."""
        tag = "regex: on" if on else "regex: off"
        self.placeholder = f"type to filter commands ...  [{tag}]"

    def on_key(self, event: Key) -> None:
        if event.key == "r":
            # Toggle regex mode without inserting the character.
            cast("AmbrosiaApp", self.app).action_toggle_regex()
            event.prevent_default()
            event.stop()
            return
        if event.key in ("enter", "tab"):
            cast("AmbrosiaApp", self.app).action_focus_results()
            event.prevent_default()
            event.stop()
            return
        if event.key == "escape":
            self.value = ""
            event.prevent_default()
            event.stop()


__all__ = ["SearchBar"]
