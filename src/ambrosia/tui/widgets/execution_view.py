"""Live output view shown while a command runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.message import Message
from textual.widget import Widget
from textual.widgets import Log, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ExecutionView(Widget):
    """Header, command line, scrolling log, and finish status for a running job."""

    class CommandFinished(Message):
        """Posted when the subprocess exits (or cannot be started)."""

        def __init__(self, exit_code: int | None, duration_ms: int) -> None:
            super().__init__()
            self.exit_code = exit_code
            self.duration_ms = duration_ms

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._header = Static(id="execution-header")
        self._command_line = Static(id="execution-command")
        self._log = Log(id="execution-log", highlight=False)
        self._status = Static(id="execution-status")

    def compose(self) -> ComposeResult:
        yield self._header
        yield self._command_line
        yield self._log
        yield self._status

    def start(self, command_name: str, argv: list[str]) -> None:
        """Show the running header and command line, clearing prior output."""
        self._header.update(f"running: {command_name}   [c]cancel   [b]back")
        self._command_line.update(" ".join(argv))
        self._log.clear()
        self._status.update("")

    def focus_log(self) -> None:
        """Focus the scrolling log so output is readable."""
        self._log.focus()

    def write_line(self, text: str) -> None:
        """Append a line of streamed subprocess output."""
        self._log.write_line(text)

    def finish(self, exit_code: int | None, duration_ms: int) -> None:
        """Show exit code and duration once the subprocess has exited."""
        self._status.update(
            f"exit code: {exit_code}   "
            f"duration: {duration_ms / 1000:.2f}s   "
            "[b]back   (select the command again to run again)"
        )
        self.post_message(self.CommandFinished(exit_code, duration_ms))


__all__ = ["ExecutionView"]
