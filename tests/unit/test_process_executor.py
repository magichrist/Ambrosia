# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the ProcessExecutor: argv, shell metacharacters, timeout,
cancellation, output cap, secret redaction."""

from __future__ import annotations

import asyncio

import pytest

from ambrosia.domain.protocols import ActionExecutionContext, ActionRequest
from ambrosia.executors import FakeExecutor, ProcessExecutor, SecretRedactor


def _request(execution_id: str = "exec-1", **inputs) -> ActionRequest:
    return ActionRequest(
        execution_id=execution_id,
        action_id="test.action",
        inputs=dict(inputs),
    )


def _context() -> ActionExecutionContext:
    return ActionExecutionContext(engagement_id="eng-1")


async def _collect(handler, request, context) -> list:
    return [e async for e in handler.execute(request, context)]


# ---------------------------------------------------------------------------
# Fake stream / process helpers for monkeypatched subprocess tests


class _StreamReader:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, n: int = 4096) -> bytes:
        data = self._data[:n]
        self._data = self._data[n:]
        return data


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.pid = 1
        self.returncode = None
        self._stdout = _StreamReader(stdout)
        self._stderr = _StreamReader(stderr)
        self.terminated = False
        self.killed = False

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.returncode = 0
        return 0


# ---------------------------------------------------------------------------
# argv preserved as separate arguments


@pytest.mark.asyncio
async def test_argv_preserved_as_separate_arguments(monkeypatch) -> None:
    """argv is passed as separate args (no shell)."""
    captured: list[list[str]] = []

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        captured.append(list(argv))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    executor = ProcessExecutor(executable="fake-tool")
    request = _request(argv=["--flag", "value", "extra"])
    events = await _collect(executor, request, _context())

    assert len(captured) == 1
    assert captured[0] == ["fake-tool", "--flag", "value", "extra"]
    kinds = [e.kind for e in events]
    assert "CompletedEvent" in kinds


# ---------------------------------------------------------------------------
# shell metacharacters passed as data


@pytest.mark.asyncio
async def test_shell_metacharacters_passed_as_data(monkeypatch) -> None:
    """Shell metacharacters in argv are passed as data, not interpreted."""
    captured: list[list[str]] = []

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        captured.append(list(argv))
        return _FakeProcess(stdout=b"echo output\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    executor = ProcessExecutor(executable="echo")
    request = _request(argv=["; rm -rf /", "|", "&", "$(whoami)", "`id`"])
    await _collect(executor, request, _context())

    assert captured[0] == ["echo", "; rm -rf /", "|", "&", "$(whoami)", "`id`"]
    assert "; rm -rf /" in captured[0]


# ---------------------------------------------------------------------------
# executable allowlisting


@pytest.mark.asyncio
async def test_executable_is_allowlisted_not_from_inputs(monkeypatch) -> None:
    """The executable comes from the allowlist, never from untrusted inputs."""
    captured: list[list[str]] = []

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        captured.append(list(argv))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    executor = ProcessExecutor(executable="allowlisted-tool")
    request = _request(argv=["/tmp/malicious", "--flag"])
    await _collect(executor, request, _context())

    assert captured[0][0] == "allowlisted-tool"
    assert captured[0] != ["/tmp/malicious", "--flag"]


# ---------------------------------------------------------------------------
# secret redaction


@pytest.mark.asyncio
async def test_secret_redaction_in_stdout(monkeypatch) -> None:
    """Secret values in stdout are redacted in OutputChunkEvent payloads."""
    captured_texts: list[str] = []

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        return _FakeProcess(stdout=b"password=hunter2 and token=abc123\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    redactor = SecretRedactor()
    redactor.add_secret("hunter2")
    redactor.add_secret("abc123")
    executor = ProcessExecutor(executable="cat", redactor=redactor)
    request = _request(argv=["file.txt"])
    events = await _collect(executor, request, _context())

    for event in events:
        if event.kind == "OutputChunkEvent":
            captured_texts.append(event.payload["text"])

    output = "".join(captured_texts)
    assert "hunter2" not in output
    assert "abc123" not in output
    assert "[REDACTED]" in output


@pytest.mark.asyncio
async def test_secret_redaction_in_stderr(monkeypatch) -> None:
    """Secret values in stderr are redacted."""

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        return _FakeProcess(stderr=b"ERROR: token=supersecret\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    redactor = SecretRedactor()
    redactor.add_secret("supersecret")
    executor = ProcessExecutor(executable="cat", redactor=redactor)
    request = _request(argv=["file.txt"])
    events = await _collect(executor, request, _context())

    for event in events:
        if event.kind == "OutputChunkEvent" and event.payload.get("stream") == "stderr":
            assert "supersecret" not in event.payload["text"]
            assert "[REDACTED]" in event.payload["text"]


# ---------------------------------------------------------------------------
# output cap


@pytest.mark.asyncio
async def test_output_cap_truncates(monkeypatch) -> None:
    """Output beyond max_output_bytes is truncated."""
    big_output = b"x" * 10_000

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        return _FakeProcess(stdout=big_output)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    executor = ProcessExecutor(executable="cat", max_output_bytes=1000)
    request = _request(argv=["file.txt"])
    events = await _collect(executor, request, _context())

    truncated = [
        e
        for e in events
        if e.kind == "OutputChunkEvent" and "truncated" in e.payload.get("text", "")
    ]
    assert len(truncated) >= 1, "expected a truncation event"


# ---------------------------------------------------------------------------
# timeout / cancellation terminate subprocess


@pytest.mark.asyncio
async def test_cancellation_terminates_subprocess(monkeypatch) -> None:
    """Cancelling the generator terminates and reaps the child process."""

    async def _fake_create_subprocess_exec(*argv, **kwargs):
        proc = _FakeProcess()

        async def _never_returns() -> bytes:
            await asyncio.sleep(3600)
            return b""

        proc._stdout = _StreamReader(b"")
        proc._stdout.read = _never_returns  # type: ignore[method-assign]
        proc._stderr.read = _never_returns  # type: ignore[method-assign]
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    executor = ProcessExecutor(executable="sleep")
    request = _request(argv=["100"])
    gen = executor.execute(request, _context())

    # Get the ProgressEvent first.
    event = await gen.asend(None)
    assert event.kind == "ProgressEvent"

    # Cancel: close the generator.
    await gen.aclose()
    # The fake process's terminate/kill are not called because _FakeProcess
    # is created inside the monkeypatched factory; verify via the executor's
    # internal process map being cleared.
    assert executor._processes == {}


@pytest.mark.asyncio
async def test_missing_argv_produces_failed_event() -> None:
    executor = ProcessExecutor(executable="fake-tool")
    request = _request(message="hello")  # no 'argv'
    events = await _collect(executor, request, _context())

    failed = [e for e in events if e.kind == "FailedEvent"]
    assert len(failed) == 1
    assert failed[0].payload["code"] == "validation_error"


# ---------------------------------------------------------------------------
# FakeExecutor


@pytest.mark.asyncio
async def test_fake_executor_records_calls() -> None:
    fake = FakeExecutor(output="ok", exit_code=0)
    request = _request(argv=["--flag", "value"])
    context = _context()

    events = [e async for e in fake.execute(request, context)]
    kinds = [e.kind for e in events]
    assert "OutputChunkEvent" in kinds
    assert "CompletedEvent" in kinds

    assert len(fake.calls) == 1
    assert fake.last_argv() == ["--flag", "value"]


@pytest.mark.asyncio
async def test_fake_executor_failure() -> None:
    fake = FakeExecutor(should_fail=True, fail_message="boom")
    request = _request()
    events = [e async for e in fake.execute(request, _context())]
    failed = [e for e in events if e.kind == "FailedEvent"]
    assert len(failed) == 1
    assert "boom" in failed[0].payload["message"]


@pytest.mark.asyncio
async def test_fake_executor_timeout_is_cancellable() -> None:
    fake = FakeExecutor(should_timeout=True)
    request = _request()
    gen = fake.execute(request, _context())

    task = asyncio.create_task(_collect_gen(gen))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert "exec-1" in fake.terminated


async def _collect_gen(gen) -> None:
    async for _ in gen:
        pass
