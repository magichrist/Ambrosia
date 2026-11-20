"""Preview panel widget: full detail of the highlighted command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.model import Command
    from ambrosia.session import SessionState


class PreviewPanel(Widget):
    """Right-hand preview: shell template, inputs, and saved session values."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._content = Static(id="preview-content")

    def compose(self) -> ComposeResult:
        yield Label("preview", id="preview-title")
        yield self._content

    def set_command(self, command: Command | None, session: SessionState) -> None:
        """Render ``command`` detail, or a placeholder when ``None``."""
        if command is None:
            self._content.update("No command selected.")
            return

        values = session.get_all(command.id)
        lines: list[str] = []
        lines.append(f"id: {command.id}")
        lines.append(f"name: {command.name}")
        if command.description:
            lines.append(f"description: {command.description}")
        if command.tags:
            lines.append(f"tags: {', '.join(command.tags)}")
        lines.append("")
        lines.append("shell:")
        lines.append(f"  {command.shell}")
        lines.append("")
        lines.append("inputs:")
        if not command.inputs:
            lines.append("  (none)")
        for input_ in command.inputs:
            required = " *" if input_.required else " "
            secret = " (secret)" if input_.secret else ""
            saved = values.get(input_.id)
            if input_.secret:
                display = "********" if saved is not None else "(not set)"
            elif saved is not None:
                display = saved
            else:
                display = "(not set)"
            lines.append(f"  [{input_.id}]{required}{secret} {input_.prompt}: {display}")
        self._content.update("\n".join(lines))


__all__ = ["PreviewPanel"]
