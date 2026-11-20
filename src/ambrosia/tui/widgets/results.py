"""Results list widget: filtered commands shown as selectable rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

if TYPE_CHECKING:
    from ambrosia.model import Command


class ResultsList(ListView):
    """A list of filtered commands; the highlighted row feeds the preview panel."""

    class CommandHighlighted(Message):
        """Posted when a different command row is highlighted."""

        def __init__(self, command: Command) -> None:
            super().__init__()
            self.command = command

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._commands: dict[str, Command] = {}

    async def set_commands(self, commands: list[Command]) -> None:
        """Replace the displayed commands with ``commands`` (already filtered).

        ``ListView.clear`` does not remove children in this Textual release, so
        existing items are removed explicitly before appending the new rows.
        The method stays async so callers can schedule it with
        ``asyncio.create_task``.
        """
        self._commands = {command.id: command for command in commands}
        await self.clear()
        for command in commands:
            await self.append(self._make_item(command))

    def _make_item(self, command: Command) -> ListItem:
        text = Text()
        text.append(command.name, style="bold")
        if command.description:
            text.append(f"  — {command.description}")
        if command.tags:
            text.append(f"  [tags: {', '.join(command.tags)}]")
        text.append("\n    ")
        text.append("shell: ", style="dim")
        text.append(command.shell)
        return ListItem(Static(text), id=command.id)

    def selected_command(self) -> Command | None:
        """Return the highlighted command, or ``None`` if nothing is selected."""
        item = self.highlighted_child
        if item is None:
            return None
        item_id = item.id
        if item_id is None:
            return None
        return self._commands.get(item_id)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        item_id = event.item.id
        if item_id is None:
            return
        command = self._commands.get(item_id)
        if command is not None:
            self.post_message(self.CommandHighlighted(command))


__all__ = ["ResultsList"]
