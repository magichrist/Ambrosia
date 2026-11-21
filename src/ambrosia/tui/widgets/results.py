"""Results list widget: filtered commands shown as selectable rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from textual.app import ComposeResult

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
        return _CommandListItem(command)

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


class _CommandListItem(ListItem):
    """A single results row: a name line and a detail line.

    The ListItem carries ``"favorite"``, ``"pinned"``, or ``"normal"`` CSS
    classes so ``app.py`` can style rows differently per category.
    """

    def __init__(self, command: Command) -> None:
        classes: list[str] = []
        if command.favorite:
            classes.append("favorite")
        if command.pinned:
            classes.append("pinned")
        if not classes:
            classes.append("normal")
        super().__init__(id=command.id, classes=" ".join(classes))
        self._command = command

    def compose(self) -> ComposeResult:
        command = self._command

        name = Text()
        if command.favorite:
            name.append("★ ", style="bold yellow")
        if command.pinned:
            name.append("▲ ", style="bold blue")
        name.append(command.name, style="bold")
        if command.description:
            name.append(f"  — {command.description}", style="dim")
        if command.tags:
            name.append(f"  [tags: {', '.join(command.tags)}]", style="dim cyan")
        if command.category:
            name.append(f"  [{command.category}]", style="magenta")

        shell = command.shell
        if len(shell) > 60:
            shell = shell[:57] + "..."
        detail = Text()
        detail.append("shell: ", style="dim")
        detail.append(shell, style="dim")

        with Vertical():
            yield Label(name, classes="name-line")
            yield Label(detail, classes="detail-line")


__all__ = ["ResultsList"]
