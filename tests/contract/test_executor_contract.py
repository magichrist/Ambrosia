# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Contract tests for executors.

Covers argv preserved as separate arguments, shell metacharacters passed as
data (not interpreted), timeout and cancellation terminating subprocess,
output cap, secret redaction in stdout/stderr/logs/previews, dry-run not
starting a subprocess, and concurrent job limit.
"""

from __future__ import annotations

import asyncio

import pytest
from tests.conftest import FakeExecutionRepository

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.models import Scope
from ambrosia.domain.protocols import ActionExecutionContext, ActionRequest
from ambrosia.engine import DryRunPlanner, JobEngine
from ambrosia.executors import FakeExecutor, ProcessExecutor, SecretRedactor
from ambrosia.policy import PolicyEngine
from ambrosia.registry import Registry


def _scope(**overrides) -> Scope:
    data = dict(
        id="scope-1",
        engagement_id="eng-1",
        include_hosts=["10.0.0.1"],
        include_cidrs=["10.0.0.0/24"],
        include_domains=["example.com"],
        exclude_hosts=["10.0.0.99"],
        exclude_cidrs=[],
        allowed_ports=[80, 443],
        max_concurrency=2,
        allowed_effects={"local_read", "network_observe"},
        require_approval_for={"local_write", "remote_change"},
    )
    data.update(overrides)
    return Scope(**data)


def _action(**overrides) -> ActionDefinition:
    data = dict(
        id="test.action",
        version="1.0.0",
        name="Test",
        description="A test action.",
        category="test",
        executor=ExecutorReference(kind="process", executable="fake-tool"),
        effects=["local_read"],
        scope_fields=["target"],
        approval_required=False,
        timeout_seconds=10,
        max_output_bytes=2_000_000,
    )
    data.update(overrides)
    return ActionDefinition(**data)


def _request(execution_id="exec-1", **inputs) -> ActionRequest:
    return ActionRequest(
        execution_id=execution_id,
        action_id="test.action",
        inputs=dict(inputs),
    )


def _context() -> ActionExecutionContext:
    return ActionExecutionContext(engagement_id="eng-1")


async def _collect(handler, request, context):
    return [e async for e in handler.execute(request, context)]


def _make_engine(concurrency_limit=2):
    registry = Registry()
    registry.register_builtin(_action(), handler=FakeExecutor())
    repo = FakeExecutionRepository()
    return JobEngine(
        registry=registry,
        execution_repository=repo,
        policy_engine=PolicyEngine(),
        concurrency_limit=concurrency_limit,
    )


# ---------------------------------------------------------------------------
# argv preserved as separate arguments

@pytest.mark.asyncio
async def test_argv_is_separate_arguments_not_a_shell_string(monkeypatch) -> None:
    captured: list[list[str]] = []

    class _EmptyStream:
        async def read(self, n=4096):
            return b""

    class FakeProc:
        pid = 1
        returncode = None

        async def wait(self):
            self.returncode = 0
            return 0

        @property
        def stdout(self):
            return _EmptyStream()

        @property
        def stderr(self):
            return _EmptyStream()

    async def _fake_exec(*argv, **kwargs):
        captured.append(list(argv))
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    executor = ProcessExecutor(executable="nmap")
    request = _request(argv=["-sS", "-p", "80", "10.0.0.1"])
    await _collect(executor, request, _context())

    assert captured[0] == ["nmap", "-sS", "-p", "80", "10.0.0.1"]


# ---------------------------------------------------------------------------
# shell metacharacters passed as data

@pytest.mark.asyncio
async def test_shell_metacharacters_are_data_not_interpreted(monkeypatch) -> None:
    captured: list[list[str]] = []

    class _EmptyStream:
        async def read(self, n=4096):
            return b""

    class FakeProc:
        pid = 1
        returncode = None

        async def wait(self):
            self.returncode = 0
            return 0

        @property
        def stdout(self):
            return _EmptyStream()

        @property
        def stderr(self):
            return _EmptyStream()

    async def _fake_exec(*argv, **kwargs):
        captured.append(list(argv))
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    executor = ProcessExecutor(executable="echo")
    request = _request(argv=["; rm -rf /", "|", "&", "$(whoami)", "`id`"])
    await _collect(executor, request, _context())

    assert captured[0] == ["echo", "; rm -rf /", "|", "&", "$(whoami)", "`id`"]


# ---------------------------------------------------------------------------
# cancellation terminates subprocess

@pytest.mark.asyncio
async def test_cancellation_terminates_subprocess(monkeypatch) -> None:
    terminated = False

    class _BlockingStream:
        async def read(self, n=4096):
            await asyncio.sleep(3600)
            return b""

    class FakeProc:
        pid = 1
        returncode = None

        def terminate(self):
            nonlocal terminated
            terminated = True

        def kill(self):
            nonlocal terminated
            terminated = True

        async def wait(self):
            self.returncode = -1
            return -1

        @property
        def stdout(self):
            return _BlockingStream()

        @property
        def stderr(self):
            return _BlockingStream()

    async def _fake_exec(*argv, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    executor = ProcessExecutor(executable="sleep")
    request = _request(argv=["100"])
    gen = executor.execute(request, _context())

    event = await gen.asend(None)
    assert event.kind == "ProgressEvent"

    await gen.aclose()
    assert terminated is True


# ---------------------------------------------------------------------------
# output cap

@pytest.mark.asyncio
async def test_output_cap_works(monkeypatch) -> None:
    big = b"x" * 10000

    class _ChunkedStream:
        def __init__(self, data):
            self._data = data

        async def read(self, n=4096):
            chunk = self._data[:n]
            self._data = self._data[n:]
            return chunk

    class _EmptyStream:
        async def read(self, n=4096):
            return b""

    class FakeProc:
        pid = 1
        returncode = None

        def terminate(self):
            pass

        def kill(self):
            pass

        async def wait(self):
            self.returncode = 0
            return 0

        @property
        def stdout(self):
            return _ChunkedStream(big)

        @property
        def stderr(self):
            return _EmptyStream()

    async def _fake_exec(*argv, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    executor = ProcessExecutor(executable="cat", max_output_bytes=1000)
    request = _request(argv=["file.txt"])
    events = await _collect(executor, request, _context())

    truncated = [
        e for e in events
        if e.kind == "OutputChunkEvent" and "truncated" in e.payload.get("text", "")
    ]
    assert len(truncated) >= 1


# ---------------------------------------------------------------------------
# secret redaction in stdout/stderr

@pytest.mark.asyncio
async def test_secret_redaction_stdout_stderr(monkeypatch) -> None:
    redacted_texts: list[str] = []

    class _SingleRead:
        def __init__(self, data):
            self._data = data

        async def read(self, n=4096):
            data = self._data
            self._data = b""
            return data

    class FakeProc:
        pid = 1
        returncode = None

        def terminate(self):
            pass

        def kill(self):
            pass

        async def wait(self):
            self.returncode = 0
            return 0

        @property
        def stdout(self):
            return _SingleRead(b"token=abc123\n")

        @property
        def stderr(self):
            return _SingleRead(b"ERR: pass=hunter2\n")

    async def _fake_exec(*argv, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    redactor = SecretRedactor()
    redactor.add_secret("abc123")
    redactor.add_secret("hunter2")
    executor = ProcessExecutor(executable="cat", redactor=redactor)
    request = _request(argv=["file.txt"])
    events = await _collect(executor, request, _context())

    for event in events:
        if event.kind == "OutputChunkEvent":
            text = event.payload["text"]
            assert "abc123" not in text
            assert "hunter2" not in text
            redacted_texts.append(text)

    assert any("[REDACTED]" in t for t in redacted_texts)


@pytest.mark.asyncio
async def test_secret_redactor_redacts_dict() -> None:
    redactor = SecretRedactor()
    redactor.add_secret("s3cr3t")
    data = {"username": "alice", "password": "s3cr3t", "token": "abc"}
    result = redactor.redact_dict(data)
    assert result["username"] == "alice"
    assert result["password"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"  # 'token' is a default secret key


# ---------------------------------------------------------------------------
# dry-run does not start subprocess

@pytest.mark.asyncio
async def test_dry_run_launches_no_process() -> None:
    fake = FakeExecutor()
    registry = Registry()
    registry.register_builtin(_action(), handler=fake)
    repo = FakeExecutionRepository()
    engine = JobEngine(
        registry=registry,
        execution_repository=repo,
        policy_engine=PolicyEngine(),
    )

    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag", "value"]},
        target_refs=["10.0.0.1"],
    )

    plan = await engine.dry_run(
        execution_id, scope=_scope(), address="10.0.0.1", port=80
    )

    assert plan["dry_run"] is True
    assert plan["executable"] == "fake-tool"
    assert plan["argv"] == ["--flag", "value"]
    assert fake.calls == []  # FakeExecutor was never invoked


# ---------------------------------------------------------------------------
# DryRunPlanner produces a sanitized plan

def test_dry_run_planner_produces_plan() -> None:
    planner = DryRunPlanner()
    plan = planner.plan(
        execution_id="exec-1",
        action_id="test.action",
        executable="fake-tool",
        argv=["--flag", "value"],
        outcome="allowed",
        reason="all clear",
        scope_address="10.0.0.1",
        effects=["local_read"],
        approval_required=False,
        timeout_seconds=10,
        max_output_bytes=2_000_000,
        decisions=[],
    )
    assert plan.executable == "fake-tool"
    assert plan.argv == ["--flag", "value"]
    assert plan.approval_required is False
    d = plan.to_dict()
    assert d["dry_run"] is True
    assert d["executable"] == "fake-tool"


# ---------------------------------------------------------------------------
# concurrent job limit

@pytest.mark.asyncio
async def test_concurrent_job_limit() -> None:
    running = 0
    max_running = 0
    lock = asyncio.Lock()

    class TrackingFake(FakeExecutor):
        async def execute(self, request, context):
            nonlocal running, max_running
            async with lock:
                running += 1
                max_running = max(max_running, running)
            try:
                await asyncio.sleep(0.05)
            finally:
                async with lock:
                    running -= 1
            async for e in super().execute(request, context):
                yield e

    fake = TrackingFake()
    registry = Registry()
    registry.register_builtin(_action(), handler=fake)
    repo = FakeExecutionRepository()
    engine = JobEngine(
        registry=registry,
        execution_repository=repo,
        policy_engine=PolicyEngine(),
        concurrency_limit=1,
    )

    ids = []
    for i in range(3):
        eid = await engine.create_job(
            engagement_id="eng-1",
            action_id="test.action",
            inputs={"argv": ["--flag"]},
            target_refs=["10.0.0.1"],
        )
        await engine.validate_job(execution_id=eid, scope=_scope(), address="10.0.0.1")
        record = engine._execution_repository.get(eid)
        record.status = "ready"
        engine._execution_repository.update(record)
        ids.append(eid)

    async def _run_one(eid: str) -> None:
        async for _ in engine.run_job(eid):
            pass

    # Launch all three concurrently; the engine semaphore (limit=1) ensures
    # only one runs at a time.
    results = await asyncio.gather(
        *[_run_one(i) for i in ids], return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            raise result

    assert max_running == 1
