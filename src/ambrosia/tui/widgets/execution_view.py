"""Live output view shown while a command runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Log, Rule, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Key


class _ExecutionLog(Log):
    """Log that returns to the workstation on left arrow instead of scrolling."""

    def on_key(self, event: Key) -> None:
        if event.key == "left":
            self.app.action_go_back()  # type: ignore[attr-defined]
            event.prevent_default()
            event.stop()


class ExecutionView(Widget):
    """Header, command line, scrolling log, and finish status for a running job."""

    class CommandFinished(Message):
        """Posted when the subprocess exits (or cannot be started)."""

        def __init__(
            self, exit_code: int | None, duration_ms: int, cancelled: bool = False
        ) -> None:
            super().__init__()
            self.exit_code = exit_code
            self.duration_ms = duration_ms
            self.cancelled = cancelled

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._header = Static(id="execution-header")
        self._command_line = Static(id="execution-command")
        self._log = _ExecutionLog(id="execution-log", highlight=False, auto_scroll=True)
        self._status = Static(id="execution-status")
        self._run_again = Button("Run again", id="run-again", variant="primary")

    def compose(self) -> ComposeResult:
        yield self._header
        yield Rule(id="execution-rule-header")
        yield self._command_line
        yield Rule(id="execution-rule-command")
        yield self._log
        yield Rule(id="execution-rule-log")
        yield self._status
        yield self._run_again

    def start(self, command_name: str, argv: list[str]) -> None:
        """Show the running header and command line, clearing prior output."""
        self._header.update(
            Text.from_markup(f"running: [bold]{command_name}[/bold]   [c]cancel   [b]back")
        )
        self._command_line.update(Text.from_markup(f"[dim]{' '.join(argv)}[/dim]"))
        self._log.clear()
        self._status.update("")
        self._run_again.display = False

    def focus_log(self) -> None:
        """Focus the scrolling log so output is readable."""
        self._log.focus()

    def write_line(self, text: str) -> None:
        """Append a line of streamed subprocess output."""
        self._log.write_line(text)

    def finish(self, exit_code: int | None, duration_ms: int, cancelled: bool = False) -> None:
        """Show exit code and duration once the subprocess has exited.

        The status line is colour-coded: green for success (exit 0), red for
        failure (non-zero), yellow for cancellation. The "Run again" button is
        revealed once the job has finished.
        """
        if cancelled:
            outcome = "[yellow]cancelled[/]"
        elif exit_code == 0:
            outcome = "[green]exit code: 0[/]"
        else:
            outcome = f"[red]exit code: {exit_code}[/]"
        self._status.update(
            f"{outcome}   "
            f"duration: {duration_ms / 1000:.2f}s   "
            "[b]back   [g]run again   (select the command again to run again)"
        )
        self._run_again.display = True
        self.post_message(self.CommandFinished(exit_code, duration_ms, cancelled))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the "Run again" button by re-running the last command."""
        if event.button.id == "run-again":
            self.app.action_run_again()  # type: ignore[attr-defined]
            event.stop()


__all__ = ["ExecutionView"]
