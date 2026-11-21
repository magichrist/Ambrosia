"""Preview panel widget: full detail of the highlighted command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
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
        text = Text()

        # Title line: command name in bold.
        text.append(command.name, style="bold")
        text.append("\n")

        # ID line: dim.
        text.append(f"id: {command.id}\n", style="dim")

        # Description: dim italic when present.
        if command.description:
            text.append(f"{command.description}\n", style="dim italic")

        # Tags: cyan chips.
        if command.tags:
            text.append("tags: ", style="dim")
            for index, tag in enumerate(command.tags):
                if index:
                    text.append(" ")
                text.append(f"[{tag}]", style="cyan")
            text.append("\n")

        # Category: dim when present.
        if command.category:
            text.append(f"category: {command.category}\n", style="dim")

        text.append("\n")

        # Shell: indented block under a dim header.
        text.append("shell:\n", style="dim")
        text.append(f"  {command.shell}\n", style="")

        text.append("\n")

        # Inputs: one line per input with required/secret markers and saved value.
        text.append("inputs:\n", style="dim")
        if not command.inputs:
            text.append("  (none)\n", style="dim")
        for input_ in command.inputs:
            text.append("  [", style="dim")
            text.append(input_.id, style="bold")
            text.append("]", style="dim")
            if input_.required:
                text.append(" *", style="red")
            if input_.secret:
                text.append(" (secret)", style="dim red")
            text.append(f" {input_.prompt}: ")
            saved = values.get(input_.id)
            if input_.secret:
                display = "********" if saved is not None else "(not set)"
            elif saved is not None:
                display = saved
            else:
                display = "(not set)"
            if saved is not None:
                text.append(display, style="green")
            else:
                text.append(display, style="dim red")
            text.append("\n")
            if input_.validation_hint:
                text.append(f"      hint: {input_.validation_hint}\n", style="dim italic")

        self._content.update(text)


__all__ = ["PreviewPanel"]
