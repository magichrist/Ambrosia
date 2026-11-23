"""Preset inspector: full detail for the highlighted preset."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widget import Widget
from textual.widgets import Label, Static

from ambrosia.tui.design import (
    GUMMY_AMBER,
    GUMMY_GREEN,
    GUMMY_LIGHT_PINK,
    GUMMY_PINK,
    PHOSPHOR,
    TEXT_MUTED,
    YELLOW,
)

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.model import Command
    from ambrosia.workflow import Workflow


class PresetInspector(Widget):
    """Right-hand panel showing the full preset and quick-run status."""

    CSS = f"""
    PresetInspector {{
        layout: vertical;
    }}
    #inspector-title {{
        color: {GUMMY_PINK};
        text-style: bold;
        height: 1;
        padding: 0 1;
    }}
    #inspector-content {{
        height: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }}
    #inspector-quick-status {{
        height: auto;
        padding: 0 1 1 1;
        color: {YELLOW};
        text-style: bold;
    }}
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._title = Label("PRESET INSPECTOR", id="inspector-title")
        self._content = Static(id="inspector-content")
        self._quick_status = Static(id="inspector-quick-status")

    def compose(self) -> ComposeResult:
        yield self._title
        yield self._content
        yield self._quick_status

    def set_quick_status(self, text: str) -> None:
        """Show a compact quick-run result line under the preset detail."""
        self._quick_status.update(text)

    def set_command(self, command: Command | None, values: dict[str, str]) -> None:
        """Render full detail for ``command``, or a placeholder when ``None``."""
        self._title.update("PRESET INSPECTOR")
        self._quick_status.update("")
        if command is None:
            self._content.update("No preset selected.")
            return

        text = Text()
        text.append(command.name, style=f"bold {PHOSPHOR}")
        if command.favorite:
            text.append("  ★", style=GUMMY_AMBER)
        text.append("\n")
        text.append(f"id: {command.id}", style=TEXT_MUTED)
        if command.description:
            text.append(f"\n\n{command.description}", style=TEXT_MUTED)
        if command.category:
            text.append(f"\n\npath: {command.category}", style=GUMMY_PINK)
        if command.tags:
            text.append("\n\ntags: ", style=TEXT_MUTED)
            for tag in command.tags:
                text.append(f"[{tag}] ", style=GUMMY_LIGHT_PINK)

        text.append("\n\nshell\n", style="bold")
        text.append(command.shell, style=PHOSPHOR)

        text.append("\n\ninputs\n", style="bold")
        if not command.inputs:
            text.append("(none)", style=TEXT_MUTED)
        for input_ in command.inputs:
            text.append(f"  [{input_.id}]", style="bold")
            if input_.required:
                text.append(" *", style=GUMMY_PINK)
            if input_.secret:
                text.append(" (secret)", style=GUMMY_AMBER)
            text.append(f" {input_.prompt}: ", style=TEXT_MUTED)
            saved = values.get(input_.id)
            if input_.secret:
                display = "********" if saved is not None else "(not set)"
            else:
                display = saved or "(not set)"
            text.append(display, style=GUMMY_GREEN if saved else TEXT_MUTED)
            if input_.validation_hint:
                text.append(f"\n      hint: {input_.validation_hint}", style=TEXT_MUTED)
        self._content.update(text)

    def set_workflow(self, workflow: Workflow) -> None:
        """Render a workflow's phases and command chain.

        Workflows are definitions, not directly runnable commands.
        """
        self._title.update("WORKFLOW INSPECTOR")
        self._quick_status.update("")

        text = Text()
        text.append(workflow.name, style=f"bold {GUMMY_PINK}")
        text.append("\n")
        text.append(f"id: {workflow.id}", style=TEXT_MUTED)
        text.append("\n")
        text.append("type: workflow", style=TEXT_MUTED)
        if workflow.description:
            text.append(f"\n\n{workflow.description}", style=TEXT_MUTED)

        text.append(
            f"\n\nphases ({len(workflow.phase_names())}) · "
            f"{workflow.command_count()} commands",
            style="bold",
        )
        if not workflow.phase_names():
            text.append("\n(no phases)", style=TEXT_MUTED)
        for phase in workflow.phase_names():
            text.append(f"\n\n{phase}", style=f"bold {GUMMY_LIGHT_PINK}")
            for command_id in workflow.command_ids(phase):
                text.append(f"\n  {command_id}", style=PHOSPHOR)
        text.append(
            "\n\nsearch an id with cmd: to find and run its preset",
            style=TEXT_MUTED,
        )
        self._content.update(text)


__all__ = ["PresetInspector"]
