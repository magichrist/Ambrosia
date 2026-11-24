"""One shared terminal-style results sidebar for workflow quick runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from ambrosia.tui.design import GUMMY_LIGHT_PINK, PHOSPHOR

if TYPE_CHECKING:
    from textual.app import ComposeResult


class WorkflowResults(Vertical):
    """Right-hand log that collects every quick-run result in a workflow session.

    Results are appended, never cleared between commands: running command A and
    then command B leaves both outputs visible, like a terminal scrollback.
    Styling lives in :class:`AmbrosiaApp`'s CSS, like the app's other panels.
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._log = RichLog(id="workflow-results-log", min_width=0, auto_scroll=True)

    def compose(self) -> ComposeResult:
        yield Static(
            Text("RESULTS · x to run", style=f"bold {PHOSPHOR}"), id="workflow-results-header"
        )
        yield self._log

    def start_command(self, command_name: str, argv: list[str]) -> None:
        """Append the executed command in the TUI's signature pink."""
        self._log.write(Text(f"$ {' '.join(argv)}", style=GUMMY_LIGHT_PINK))

    def write_output(self, text: str) -> None:
        """Append streamed subprocess output to the shared log."""
        for line in text.splitlines() or [text]:
            self._log.write(line)

    def write_status(
        self, exit_code: int | None, duration_ms: int, cancelled: bool = False
    ) -> None:
        """Append the final status line for a finished run."""
        if cancelled:
            outcome = "cancelled"
        elif exit_code == 0:
            outcome = "exit code: 0"
        else:
            outcome = f"exit code: {exit_code}"
        self._log.write(f"{outcome}   duration: {duration_ms / 1000:.2f}s")

    def write_message(self, text: str) -> None:
        """Append an informational line (copy, scope block, error)."""
        self._log.write(text)

    def clear(self) -> None:
        """Erase all accumulated results (ctrl+x in the workflow view)."""
        self._log.clear()


__all__ = ["WorkflowResults"]
