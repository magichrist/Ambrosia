"""Preset explorer: ranked search results as compact, hoverable rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from ambrosia.tui.design import PHOSPHOR, TEXT_MUTED
from ambrosia.tui.ids import safe_widget_id

if TYPE_CHECKING:
    from ambrosia.model import Command
    from ambrosia.tui.matching import SearchResult


class PresetExplorer(ListView):
    """A list of matching presets; the highlighted row feeds the inspector."""

    class PresetHighlighted(Message):
        """Posted when a different preset row is highlighted."""

        def __init__(self, command: Command) -> None:
            super().__init__()
            self.command = command

    class PresetActivated(Message):
        """Posted when Enter is pressed on a preset row."""

        def __init__(self, command: Command) -> None:
            super().__init__()
            self.command = command

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._results: list[SearchResult] = []
        self._commands: dict[str, Command] = {}
        self._item_counter = 0

    async def set_results(self, results: list[SearchResult]) -> None:
        """Replace the displayed presets with ranked search results."""
        self._results = list(results)
        self._commands = {}
        self._item_counter = 0
        await self.clear()
        for result in results:
            command = result.command
            # Unique widget ids: presets from different directories may share
            # a command id, and duplicate ids raise DuplicateIds in Textual.
            item_id = safe_widget_id(f"preset_{command.id}_{self._item_counter}")
            self._item_counter += 1
            self._commands[item_id] = command
            await self.append(self._make_item(command, item_id))
        # Highlight the best match so the inspector is populated and Enter can
        # run immediately without requiring an initial arrow key.
        self.index = 0 if results else None

    def _make_item(self, command: Command, item_id: str) -> ListItem:
        # Compact row: just "name: description". Full detail lives in the
        # inspector and in the hover tooltip.
        label = Text()
        label.append(command.name, style=f"bold {PHOSPHOR}")
        label.append(": ", style=TEXT_MUTED)
        label.append(command.description or command.shell or command.id, style=TEXT_MUTED)
        item = ListItem(Static(label), id=item_id)
        item.tooltip = self._tooltip_text(command)
        return item

    @staticmethod
    def _tooltip_text(command: Command) -> Text:
        """Build the full-detail text shown when hovering a result row."""
        tip = Text()
        tip.append(command.name, style="bold")
        tip.append(f"\nid: {command.id}", style=TEXT_MUTED)
        if command.category:
            tip.append(f"\npath: {command.category}", style=TEXT_MUTED)
        if command.tags:
            tip.append(f"\ntags: {', '.join(command.tags)}", style=TEXT_MUTED)
        tip.append("\n\nshell:", style="bold")
        tip.append(f"\n{command.shell}", style=PHOSPHOR)
        if command.inputs:
            tip.append("\n\ninputs:", style="bold")
            for input_ in command.inputs:
                required = " *" if input_.required else ""
                secret = " (secret)" if input_.secret else ""
                tip.append(f"\n  [{input_.id}]{required}{secret} {input_.prompt}", style=TEXT_MUTED)
        return tip

    def selected_command(self) -> Command | None:
        """Return the highlighted command, or ``None`` when nothing is selected."""
        item = self.highlighted_child
        if item is None or item.id is None:
            return None
        return self._commands.get(item.id)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or event.item.id is None:
            return
        command = self._commands.get(event.item.id)
        if command is not None:
            self.post_message(self.PresetHighlighted(command))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Translate ListView's Enter into an explicit preset activation."""
        if event.item is None or event.item.id is None:
            return
        command = self._commands.get(event.item.id)
        if command is not None:
            self.post_message(self.PresetActivated(command))
        event.stop()


__all__ = ["PresetExplorer"]
