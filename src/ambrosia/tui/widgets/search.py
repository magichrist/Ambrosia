"""Search bar widget: live, debounced filtering with search-mode cycling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from textual.widgets import Input

if TYPE_CHECKING:
    from textual.events import Key

    from ambrosia.tui.app import AmbrosiaApp

SearchMode = Literal["substring", "fuzzy", "regex"]

# Placeholder hint shown for each search mode. The mode tag is shown first and
# in uppercase so the current mode is visible at a glance, without relying on
# the separate status line.
_MODE_PLACEHOLDERS: dict[SearchMode, str] = {
    "substring": "[SUBSTRING] type to filter commands ...",
    "fuzzy": "[FUZZY] type to filter commands ...",
    "regex": "[REGEX] type to filter commands ...",
}


class SearchBar(Input):
    """The search input.

    The search bar is an :class:`~textual.widgets.Input` so that it owns its
    focus and its ``Input.Changed`` message (which bubbles up to the
    application for debounced filtering). Pressing ``r`` toggles regex mode
    on/off and pressing ``f`` cycles the search mode (substring → fuzzy →
    regex → substring) without inserting the character; ``Tab``/``Enter``
    move focus to the results.

    The current search mode is shown as an uppercase bracketed tag at the start
    of the placeholder so it remains visible while the input is empty.
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(
            id=id,
            placeholder=_MODE_PLACEHOLDERS["substring"],
        )

    def focus_input(self) -> None:
        """Focus the search input (this widget is the input)."""
        self.focus()

    def set_search_mode(self, mode: SearchMode) -> None:
        """Update the search mode and the input placeholder hint."""
        self.placeholder = _MODE_PLACEHOLDERS[mode]

    def on_key(self, event: Key) -> None:
        if event.key == "r":
            # Toggle regex mode on/off without inserting the character.
            cast("AmbrosiaApp", self.app).action_toggle_regex()
            event.prevent_default()
            event.stop()
            return
        if event.key == "f":
            # Cycle search modes without inserting the character.
            cast("AmbrosiaApp", self.app).action_cycle_search_mode()
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


__all__ = ["SearchBar", "SearchMode"]
