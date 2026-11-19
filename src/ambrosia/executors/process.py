"""Process executor: asyncio.create_subprocess_exec with shell=False semantics.

Runs an allowlisted executable with argv arrays only. Never interpolates values
into a shell command string. Streams stdout/stderr with secret redaction and
output size limits. Supports timeout and cancellation with child-process
termination and reaping.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from ambrosia.domain.errors import ExecutionError
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionRequest,
    ExecutionEvent,
)
from ambrosia.executors.base import ExecutorResult, SecretRedactor


class ProcessExecutor:
    """Executes a fixed, allowlisted executable with argv arrays only.

    ``executable`` is the allowlisted name/ID from the action definition -- it
    is never sourced from an untrusted preset. Arguments come from
    ``request.inputs["argv"]`` (a list of strings) and are passed as data,
    never interpreted by a shell.
    """

    def __init__(
        self,
        *,
        executable: str,
        redactor: SecretRedactor | None = None,
        max_output_bytes: int = 2_000_000,
    ) -> None:
        if not executable or not executable.strip():
            message = "process executor requires a non-empty executable"
            raise ValueError(message)
        self._executable = executable.strip()
        self._redactor = redactor or SecretRedactor()
        self._max_output_bytes = max_output_bytes
        self._processes: dict[str, asyncio.Process] = {}

    # ------------------------------------------------------------------ execute

    async def execute(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run the allowlisted executable with resolved argv.

        ``request.inputs`` must include ``argv`` as a ``list[str]`` of
        arguments (not including the executable). The executable is the
        allowlisted value from the action definition.
        """
        execution_id = request.execution_id

        argv_inputs = request.inputs.get("argv")
        if (
            not isinstance(argv_inputs, list)
            or not all(isinstance(arg, str) for arg in argv_inputs)
        ):
            yield ExecutionEvent(
                kind="FailedEvent",
                execution_id=execution_id,
                payload={
                    "code": "validation_error",
                    "message": "process action inputs must include 'argv' as a list of strings",
                    "retryable": False,
                },
            )
            return

        # argv array: allowlisted executable first, then resolved arguments.
        # The executable is never supplied through an untrusted preset.
        argv = [self._executable] + list(argv_inputs)

        process: asyncio.Process | None = None
        pump_tasks: list[asyncio.Task[None]] = []
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        total_bytes = 0
        capped = False
        start_time = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._processes[execution_id] = process

            stdout_stream = process.stdout
            stderr_stream = process.stderr
            if stdout_stream is None or stderr_stream is None:
                message = "subprocess streams unexpectedly unavailable"
                raise ExecutionError(message)

            yield ExecutionEvent(
                kind="ProgressEvent",
                execution_id=execution_id,
                payload={
                    "message": f"started {self._executable}",
                    "pid": process.pid,
                    "argv": argv,
                },
            )

            queue: asyncio.Queue[ExecutionEvent | None] = asyncio.Queue()

            async def _pump(
                stream: asyncio.StreamReader, stream_name: str
            ) -> None:
                try:
                    nonlocal total_bytes, capped
                    while True:
                        if capped:
                            await queue.put(None)
                            return
                        data = await stream.read(4096)
                        if not data:
                            await queue.put(None)
                            return
                        text = data.decode("utf-8", errors="replace")
                        redacted = self._redactor.redact(text)
                        total_bytes += len(data)
                        if total_bytes > self._max_output_bytes:
                            capped = True
                            await queue.put(
                                ExecutionEvent(
                                    kind="OutputChunkEvent",
                                    execution_id=execution_id,
                                    payload={
                                        "stream": stream_name,
                                        "text": (
                                            f"[output truncated at {self._max_output_bytes} bytes]"
                                        ),
                                    },
                                )
                            )
                            # Terminate to avoid deadlocking on a full pipe.
                            if process is not None and process.returncode is None:
                                process.terminate()
                            await queue.put(None)
                            return
                        if stream_name == "stdout":
                            stdout_parts.append(redacted)
                        else:
                            stderr_parts.append(redacted)
                        await queue.put(
                            ExecutionEvent(
                                kind="OutputChunkEvent",
                                execution_id=execution_id,
                                payload={"stream": stream_name, "text": redacted},
                            )
                        )
                finally:
                    # Always signal stream end so the main loop cannot hang if
                    # a pump exits early due to an error.
                    try:
                        await queue.put(None)
                    except Exception:
                        pass

            pump_tasks = [
                asyncio.create_task(_pump(stdout_stream, "stdout")),
                asyncio.create_task(_pump(stderr_stream, "stderr")),
            ]

            pending = len(pump_tasks)
            while pending > 0:
                event = await queue.get()
                if event is None:
                    pending -= 1
                    continue
                yield event

            await asyncio.gather(*pump_tasks)

            returncode = await process.wait()
            duration = time.monotonic() - start_time

            yield ExecutionEvent(
                kind="CompletedEvent",
                execution_id=execution_id,
                payload={
                    "summary": {
                        "exit_code": returncode,
                        "duration_seconds": duration,
                        "stdout": "".join(stdout_parts),
                        "stderr": "".join(stderr_parts),
                        "stdout_bytes": sum(len(s.encode()) for s in stdout_parts),
                        "stderr_bytes": sum(len(s.encode()) for s in stderr_parts),
                        "truncated": capped,
                    },
                },
            )

        except asyncio.CancelledError:
            # Operator cancellation or timeout via wait_for: terminate and reap
            # the child process, then re-raise.
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            for task in pump_tasks:
                task.cancel()
            raise
        except GeneratorExit:
            # aclose() was called on the generator: terminate the child
            # process, cancel pumps, and re-raise GeneratorExit so the
            # generator closes properly.
            if process is not None and process.returncode is None:
                process.terminate()
            for task in pump_tasks:
                task.cancel()
            raise
        except Exception as exc:  # noqa: BLE001 - translate to typed error
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            for task in pump_tasks:
                task.cancel()
            yield ExecutionEvent(
                kind="FailedEvent",
                execution_id=execution_id,
                payload={
                    "code": "execution_error",
                    "message": str(exc),
                    "retryable": False,
                },
            )
            raise ExecutionError(str(exc)) from exc
        finally:
            self._processes.pop(execution_id, None)

    # ------------------------------------------------------------------ control

    async def terminate(self, execution_id: str) -> None:
        """Terminate and reap the process for ``execution_id`` if running."""
        process = self._processes.get(execution_id)
        if process is None:
            return
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            process.kill()
            await process.wait()

    def result_for(self, execution_id: str) -> ExecutorResult | None:
        """Best-effort result snapshot (caller should rely on events)."""
        process = self._processes.get(execution_id)
        if process is None:
            return None
        return ExecutorResult(
            execution_id=execution_id,
            exit_code=process.returncode,
        )


__all__ = ["ProcessExecutor"]
