"""Phased workflow runner: browse phases and execute a command from one."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Static

from ambrosia.tui.design import (
    GUMMY_LIGHT_PINK,
    GUMMY_PINK,
    PHOSPHOR,
    SELECTED_BG,
    TEXT_MUTED,
)

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Key

    from ambrosia.model import Command
    from ambrosia.workflow import Workflow


class _PhaseCommandList(ListView):
    """Command list whose left/right keys switch workflow phases."""

    def on_key(self, event: Key) -> None:
        if event.key == "left":
            asyncio.create_task(self.app.action_workflow_prev_phase())  # type: ignore[attr-defined]
            event.prevent_default()
            event.stop()
        elif event.key == "right":
            asyncio.create_task(self.app.action_workflow_next_phase())  # type: ignore[attr-defined]
            event.prevent_default()
            event.stop()


class WorkflowView(Widget):
    """Shows one phase of a workflow and the presets available in it."""

    class CommandChosen(Message):
        """Posted when Enter is pressed on a command in the current phase."""

        def __init__(self, command_id: str) -> None:
            super().__init__()
            self.command_id = command_id

    CSS = f"""
    #workflow-header {{
        height: 1;
        padding: 0 1;
        color: {PHOSPHOR};
        background: {SELECTED_BG};
    }}
    #workflow-phase {{
        height: 1;
        padding: 0 1;
        color: {GUMMY_LIGHT_PINK};
        text-style: bold;
    }}
    #workflow-commands {{
        height: 1fr;
    }}
    #workflow-hint {{
        height: 1;
        padding: 0 1;
        color: {TEXT_MUTED};
    }}
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._header = Static(id="workflow-header")
        self._phase = Static(id="workflow-phase")
        self._commands = _PhaseCommandList(id="workflow-commands")
        hint = Text()
        hint.append("↑/↓ ", style="bold")
        hint.append("command   ")
        hint.append("←/→ ", style="bold")
        hint.append("phase (← exits on 1)   ")
        hint.append("Enter ", style="bold")
        hint.append("run   ")
        hint.append("Esc ", style="bold")
        hint.append("back to search")
        self._hint = Static(hint, id="workflow-hint")
        self._workflow: Workflow | None = None
        self._phase_index = 0
        self._available: dict[str, Command] = {}

    def compose(self) -> ComposeResult:
        yield self._header
        yield self._phase
        yield self._commands
        yield self._hint

    async def set_workflow(
        self, workflow: Workflow, available: dict[str, Command], phase_index: int, command_index: int
    ) -> None:
        """Render ``phase_index`` of ``workflow`` and highlight ``command_index``."""
        self._workflow = workflow
        self._available = available
        self._phase_index = phase_index
        names = workflow.phase_names()
        self._header.update(
            Text.from_markup(
                f"workflow: [bold]{workflow.name}[/bold]   "
                f"[b]{phase_index + 1}/{len(names)}[/b]   [dim]Esc back[/dim]"
            )
        )
        if not names:
            self._phase.update("no phases defined")
            await self._commands.clear()
            self._commands.index = None
            return

        phase_name = names[phase_index]
        command_ids = workflow.command_ids(phase_name)
        self._phase.update(f"phase {phase_index + 1}: {phase_name}  ({len(command_ids)} commands)")

        rows: list[ListItem] = []
        for command_id in command_ids:
            label = Text()
            command = available.get(command_id)
            if command is None:
                label.append(f"{command_id} ", style=f"bold {TEXT_MUTED}")
                label.append("(preset not found)", style=f"italic {GUMMY_PINK}")
            else:
                label.append(f"{command.name} ", style=f"bold {PHOSPHOR}")
                label.append(command_id, style=TEXT_MUTED)
            rows.append(ListItem(Static(label), id=f"wf_cmd_{len(rows)}"))

        await self._commands.clear()
        for row in rows:
            await self._commands.append(row)
        self._commands.index = min(command_index, len(rows) - 1) if rows else None

    def selected_command_id(self) -> str | None:
        """Return the command id highlighted in the current phase."""
        if self._workflow is None:
            return None
        names = self._workflow.phase_names()
        if not names:
            return None
        command_ids = self._workflow.command_ids(names[self._phase_index])
        index = self._commands.index
        if index is None or not 0 <= index < len(command_ids):
            return None
        return command_ids[index]

    def selected_index(self) -> int:
        """Return the highlighted command's index in the current phase."""
        return self._commands.index or 0

    def focus_list(self) -> None:
        """Give the command list focus so arrows and Enter work immediately."""
        self._commands.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        command_id = self.selected_command_id()
        if command_id is not None:
            self.post_message(self.CommandChosen(command_id))
        event.stop()


__all__ = ["WorkflowView"]
