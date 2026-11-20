"""Shell executor for the v2 command launcher.

:func:`build_argv` is a pure function: it substitutes ``{{input_id}}`` tokens in
a shell template with resolved values, then splits the template into an argv
array on whitespace. :class:`ShellExecutor` launches that argv array with
shell=False semantics via :func:`asyncio.create_subprocess_exec`, streams
output to an optional callback, and returns a :class:`CommandResult`.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class ExecutableNotFoundError(Exception):
    """Raised when the executable in a command's argv cannot be found."""


@dataclass
class CommandResult:
    """Outcome of a command run."""

    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    cancelled: bool = False


def build_argv(shell: str, values: dict[str, str]) -> list[str]:
    """Build the argv array for a shell template from resolved ``values``.

    Each ``{{input_id}}`` token in ``shell`` is replaced with the corresponding
    value from ``values`` (missing values leave the token in place). The
    resulting shell string is then split on whitespace into an argv array
    suitable for :func:`asyncio.create_subprocess_exec`. The executable is the
    first whitespace-delimited token of the template.

    Pure function: no subprocess, no side effects.
    """
    for input_id, value in values.items():
        shell = shell.replace("{{" + input_id + "}}", value)
    return shell.split()


class ShellExecutor:
    """Run a shell template as an argv array via asyncio subprocess.

    The executable is part of the shell template (from the command catalog), so
    it is never sourced from untrusted input at run time.
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None

    # ------------------------------------------------------------------ run

    async def run(
        self,
        shell: str,
        values: dict[str, str],
        on_output: Callable[[str], object] | None = None,
    ) -> CommandResult:
        """Run ``shell`` with resolved ``values`` and return a :class:`CommandResult`.

        Output is streamed to ``on_output`` (if provided) as it arrives.
        """
        argv = build_argv(shell, values)
        executable = argv[0] if argv else ""
        if executable and shutil.which(executable) is None:
            message = f"executable not found: {executable}"
            raise ExecutableNotFoundError(message)

        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = process

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        start_time = time.monotonic()

        stdout_stream = process.stdout
        stderr_stream = process.stderr
        if stdout_stream is None or stderr_stream is None:
            message = "subprocess streams unexpectedly unavailable"
            raise RuntimeError(message)

        async def _pump(stream: asyncio.StreamReader, sink: list[str]) -> None:
            while True:
                data = await stream.read(4096)
                if not data:
                    return
                text = data.decode("utf-8", errors="replace")
                sink.append(text)
                if on_output is not None:
                    result = on_output(text)
                    if asyncio.iscoroutine(result):
                        await result

        await asyncio.gather(
            _pump(stdout_stream, stdout_parts),
            _pump(stderr_stream, stderr_parts),
        )

        returncode = await process.wait()
        duration_ms = int((time.monotonic() - start_time) * 1000)
        self._process = None
        return CommandResult(
            exit_code=returncode,
            duration_ms=duration_ms,
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
        )

    # ------------------------------------------------------------------ control

    def cancel(self) -> None:
        """Terminate (and, if needed, kill) the running subprocess."""
        process = self._process
        if process is None or process.returncode is not None:
            return
        process.terminate()
        self._process = None
