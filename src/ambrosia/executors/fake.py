"""Fake executor for tests.

Simulates execution without starting any subprocess. Records the requests it
receives so tests can assert argv preservation, shell-metacharacter handling,
and lifecycle behaviour. Supports configurable failure, timeout, and cancellation
modes.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionRequest,
    ExecutionEvent,
)


class FakeExecutor:
    """In-process fake executor implementing the ActionHandler protocol.

    No subprocess is ever started. Calls are recorded in ``calls`` for test
    assertions. Use ``set_outcome`` to simulate success, failure, or timeout.
    """

    def __init__(
        self,
        *,
        output: str = "fake output",
        exit_code: int = 0,
        should_fail: bool = False,
        should_timeout: bool = False,
        fail_message: str = "simulated failure",
    ) -> None:
        self._output = output
        self._exit_code = exit_code
        self._should_fail = should_fail
        self._should_timeout = should_timeout
        self._fail_message = fail_message
        self.calls: list[tuple[ActionRequest, ActionExecutionContext]] = []
        self.terminated: list[str] = []

    # ------------------------------------------------------------------ execute

    async def execute(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]:
        """Simulate execution and yield events."""
        self.calls.append((request, context))
        execution_id = request.execution_id

        if self._should_timeout:
            # Simulate a process that never finishes: sleep forever until
            # cancelled.
            try:
                await asyncio.sleep(float("inf"))
            except asyncio.CancelledError:
                self.terminated.append(execution_id)
                raise
            return  # pragma: no cover - unreachable unless sleep returns

        yield ExecutionEvent(
            kind="ProgressEvent",
            execution_id=execution_id,
            payload={"message": "fake execution started", "executable": "fake"},
        )

        if self._should_fail:
            yield ExecutionEvent(
                kind="FailedEvent",
                execution_id=execution_id,
                payload={
                    "code": "execution_error",
                    "message": self._fail_message,
                    "retryable": False,
                },
            )
            return

        # Stream the (fake) output as data, never interpreted by a shell.
        argv = request.inputs.get("argv", [])
        if isinstance(argv, list):
            text = " ".join(str(a) for a in argv)
        else:
            text = str(request.inputs.get("message", self._output))
        yield ExecutionEvent(
            kind="OutputChunkEvent",
            execution_id=execution_id,
            payload={"stream": "stdout", "text": text},
        )

        yield ExecutionEvent(
            kind="CompletedEvent",
            execution_id=execution_id,
            payload={
                "summary": {
                    "exit_code": self._exit_code,
                    "stdout": text,
                    "stderr": "",
                    "duration_seconds": 0.0,
                },
            },
        )

    # ------------------------------------------------------------------ control

    async def terminate(self, execution_id: str) -> None:
        """Record a termination request (no real process to terminate)."""
        self.terminated.append(execution_id)

    def result_for(self, execution_id: str) -> object:
        return None

    def last_argv(self) -> list[str] | None:
        """Return the argv from the last call, or None if never called."""
        if not self.calls:
            return None
        request = self.calls[-1][0]
        argv = request.inputs.get("argv")
        return list(argv) if isinstance(argv, list) else None

    def last_executable(self) -> str | None:
        """Return the executable implied by the last call (fake always 'fake')."""
        if not self.calls:
            return None
        return "fake"


__all__ = ["FakeExecutor"]
