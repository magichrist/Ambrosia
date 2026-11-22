"""Search input for the preset explorer."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.widgets import Input

from ambrosia.tui.matching import SearchMode, SearchQuery, parse_search_query

if TYPE_CHECKING:
    from textual.events import Key

    from ambrosia.tui.app import AmbrosiaApp
    from ambrosia.tui.widgets.results import PresetExplorer

_MODE_PLACEHOLDERS: dict[SearchMode, str] = {
    "substring": "[SUBSTRING] search name, command, tags, path ...",
    "fuzzy": "[FUZZY] search name, command, tags, path ...",
    "regex": "[REGEX] search name, command, tags, path ...",
}


class SearchBar(Input):
    """Debounced search input; ``ctrl+r`` cycles modes without inserting text."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(placeholder=_MODE_PLACEHOLDERS["substring"], id=id)

    def set_search_mode(self, mode: SearchMode) -> None:
        """Update the placeholder for the current search mode."""
        self.placeholder = _MODE_PLACEHOLDERS[mode]

    def parsed_query(self) -> SearchQuery:
        """Parse the current input into a :class:`SearchQuery`."""
        app = cast("AmbrosiaApp", self.app)
        return parse_search_query(self.value, app.search_mode)

    def focus_input(self) -> None:
        """Focus the input and place the cursor at the end."""
        self.focus()
        self.cursor_position = len(self.value)

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+r":
            cast("AmbrosiaApp", self.app).action_cycle_search_mode()
            event.prevent_default()
            event.stop()
        elif event.key in ("up", "down"):
            # Move the result highlight without leaving the search field, so
            # the operator can type and browse matches in one flow.
            app = cast("AmbrosiaApp", self.app)
            explorer = cast(
                "PresetExplorer", app.query_one("#preset-explorer")
            )
            if event.key == "down":
                explorer.action_cursor_down()
            else:
                explorer.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key in ("enter", "tab"):
            cast("AmbrosiaApp", self.app).action_focus_explorer()
            event.prevent_default()
            event.stop()


__all__ = ["SearchBar", "SearchMode", "SearchQuery", "parse_search_query"]
