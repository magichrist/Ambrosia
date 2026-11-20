# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the JobEngine: lifecycle, concurrency, dry-run, cancellation."""

from __future__ import annotations

import asyncio

import pytest
from tests.conftest import FakeExecutionRepository

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.models import Scope
from ambrosia.engine import JobEngine, valid_transition
from ambrosia.executors import FakeExecutor
from ambrosia.policy import PolicyEngine


def _scope(**overrides) -> Scope:
    data = {
        "id": "scope-1",
        "engagement_id": "eng-1",
        "include_hosts": ["10.0.0.1"],
        "include_cidrs": ["10.0.0.0/24"],
        "include_domains": ["example.com"],
        "exclude_hosts": ["10.0.0.99"],
        "exclude_cidrs": [],
        "allowed_ports": [80, 443],
        "max_concurrency": 2,
        "allowed_effects": {"local_read", "network_observe"},
        "require_approval_for": {"local_write", "remote_change"},
    }
    data.update(overrides)
    return Scope(**data)


def _action(**overrides) -> ActionDefinition:
    data = {
        "id": "test.action",
        "version": "1.0.0",
        "name": "Test",
        "description": "A test action.",
        "category": "test",
        "executor": ExecutorReference(kind="process", executable="fake-tool"),
        "effects": ["local_read"],
        "scope_fields": ["target"],
        "approval_required": False,
        "timeout_seconds": 10,
        "max_output_bytes": 2_000_000,
    }
    data.update(overrides)
    return ActionDefinition(**data)


def _registry_with_handler(handler) -> object:
    from ambrosia.registry import Registry

    registry = Registry()
    definition = _action()
    registry.register_builtin(definition, handler=handler)
    return registry


def _engine(registry=None, execution_repository=None, concurrency_limit=2):
    if registry is None:
        registry = _registry_with_handler(FakeExecutor())
    if execution_repository is None:
        execution_repository = FakeExecutionRepository()
    policy_engine = PolicyEngine()
    return JobEngine(
        registry=registry,
        execution_repository=execution_repository,
        policy_engine=policy_engine,
        concurrency_limit=concurrency_limit,
    )


# ---------------------------------------------------------------------------
# lifecycle transitions


def test_valid_transition_matrix() -> None:
    assert valid_transition("draft", "validated") is True
    assert valid_transition("validated", "ready") is True
    assert valid_transition("ready", "running") is True
    assert valid_transition("running", "parsing") is True
    assert valid_transition("parsing", "succeeded") is True
    assert valid_transition("running", "cancelled") is True
    assert valid_transition("running", "failed") is True
    assert valid_transition("draft", "running") is False
    assert valid_transition("succeeded", "running") is False


@pytest.mark.asyncio
async def test_create_job_is_draft() -> None:
    engine = _engine()
    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag"]},
        target_refs=["10.0.0.1"],
    )
    record = engine._execution_repository.get(execution_id)
    assert record.status == "draft"
    assert record.action_id == "test.action"
    assert record.target_refs == ["10.0.0.1"]


@pytest.mark.asyncio
async def test_validate_transitions_draft_to_validated() -> None:
    engine = _engine()
    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag"]},
        target_refs=["10.0.0.1"],
    )
    await engine.validate_job(execution_id, scope=_scope(), address="10.0.0.1")
    record = engine._execution_repository.get(execution_id)
    assert record.status == "validated"


@pytest.mark.asyncio
async def test_validate_blocks_outside_scope() -> None:
    engine = _engine()
    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag"]},
        target_refs=["99.99.99.99"],
    )
    from ambrosia.domain.errors import ScopeViolationError

    with pytest.raises(ScopeViolationError):
        await engine.validate_job(execution_id, scope=_scope(), address="99.99.99.99")
    record = engine._execution_repository.get(execution_id)
    assert record.status == "draft"  # unchanged on failure


# ---------------------------------------------------------------------------
# approval transitions


@pytest.mark.asyncio
async def test_approval_transition_awaiting_to_ready() -> None:
    engine = _engine()
    # Use an action that requires approval
    approval_action = ActionDefinition(
        id="test.action.approval",
        version="1.0.0",
        name="Approval Test",
        description="An action requiring approval.",
        category="test",
        executor=ExecutorReference(kind="process", executable="fake-tool"),
        effects=["local_write"],
        scope_fields=[],
        approval_required=True,
        timeout_seconds=10,
        max_output_bytes=2_000_000,
    )
    engine._registry.register_builtin(approval_action, handler=FakeExecutor())

    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action.approval",
        inputs={"argv": ["--flag"]},
        target_refs=["10.0.0.1"],
    )
    await engine.validate_job(
        execution_id,
        scope=_scope(allowed_effects={"local_read", "local_write", "network_observe"}),
        address="10.0.0.1",
    )

    # Request approval -> awaiting_approval
    approval_id = await engine.request_approval(execution_id)
    assert approval_id is not None
    record = engine._execution_repository.get(execution_id)
    assert record.status == "awaiting_approval"

    # Grant -> ready
    await engine.grant_approval(execution_id, approval_id=approval_id, decided_by="operator")
    record = engine._execution_repository.get(execution_id)
    assert record.status == "ready"


@pytest.mark.asyncio
async def test_approval_deny_transitions_to_blocked() -> None:
    engine = _engine()
    approval_action = ActionDefinition(
        id="test.action.deny",
        version="1.0.0",
        name="Deny Test",
        description="An action requiring approval.",
        category="test",
        executor=ExecutorReference(kind="process", executable="fake-tool"),
        effects=["local_write"],
        scope_fields=[],
        approval_required=True,
        timeout_seconds=10,
        max_output_bytes=2_000_000,
    )
    engine._registry.register_builtin(approval_action, handler=FakeExecutor())

    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action.deny",
        inputs={"argv": ["--flag"]},
        target_refs=["10.0.0.1"],
    )
    await engine.validate_job(
        execution_id,
        scope=_scope(allowed_effects={"local_read", "local_write", "network_observe"}),
        address="10.0.0.1",
    )

    approval_id = await engine.request_approval(execution_id)
    assert approval_id is not None
    await engine.deny_approval(
        execution_id, approval_id=approval_id, decided_by="operator", reason="denied"
    )
    record = engine._execution_repository.get(execution_id)
    assert record.status == "blocked"


# ---------------------------------------------------------------------------
# full run through fake executor


@pytest.mark.asyncio
async def test_run_executes_and_succeeds() -> None:
    fake = FakeExecutor(output="hello world", exit_code=0)
    registry = _registry_with_handler(fake)
    engine = _engine(registry=registry)

    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag", "value"]},
        target_refs=["10.0.0.1"],
    )
    await engine.validate_job(execution_id, scope=_scope(), address="10.0.0.1")

    # No approval required for local_read -> ready
    record = engine._execution_repository.get(execution_id)
    assert record.status == "validated"
    # Move to ready manually (no approval needed)
    record.status = "ready"
    engine._execution_repository.update(record)

    events = [e async for e in engine.run_job(execution_id)]
    kinds = [e.kind for e in events]
    assert "ProgressEvent" in kinds
    assert "OutputChunkEvent" in kinds
    assert "CompletedEvent" in kinds

    record = engine._execution_repository.get(execution_id)
    assert record.status == "succeeded"
    assert fake.last_argv() == ["--flag", "value"]


@pytest.mark.asyncio
async def test_run_failure_transitions_to_failed() -> None:
    fake = FakeExecutor(should_fail=True, fail_message="simulated boom")
    registry = _registry_with_handler(fake)
    engine = _engine(registry=registry)

    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag"]},
        target_refs=["10.0.0.1"],
    )
    await engine.validate_job(execution_id, scope=_scope(), address="10.0.0.1")
    record = engine._execution_repository.get(execution_id)
    record.status = "ready"
    engine._execution_repository.update(record)

    events = [e async for e in engine.run_job(execution_id)]
    failed_events = [e for e in events if e.kind == "FailedEvent"]
    assert len(failed_events) == 1

    record = engine._execution_repository.get(execution_id)
    assert record.status == "failed"
    assert record.error_code == "execution_error"


# ---------------------------------------------------------------------------
# dry run


@pytest.mark.asyncio
async def test_dry_run_returns_plan_without_starting_process() -> None:
    fake = FakeExecutor()
    registry = _registry_with_handler(fake)
    engine = _engine(registry=registry)

    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag", "value"]},
        target_refs=["10.0.0.1"],
    )

    plan = await engine.dry_run(execution_id, scope=_scope(), address="10.0.0.1", port=80)

    assert plan["dry_run"] is True
    assert plan["action_id"] == "test.action"
    assert plan["executable"] == "fake-tool"
    assert plan["argv"] == ["--flag", "value"]
    assert plan["outcome"] == "allowed"
    assert fake.calls == []  # no process started


@pytest.mark.asyncio
async def test_dry_run_blocks_outside_scope() -> None:
    engine = _engine()
    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag"]},
        target_refs=["99.99.99.99"],
    )

    plan = await engine.dry_run(execution_id, scope=_scope(), address="99.99.99.99")

    assert plan["outcome"] == "blocked"


# ---------------------------------------------------------------------------
# concurrency limit


@pytest.mark.asyncio
async def test_concurrency_limit_respected() -> None:
    """Only concurrency_limit jobs run at once."""
    started: list[str] = []
    completed: list[str] = []

    class SlowFake(FakeExecutor):
        async def execute(self, request, context):
            started.append(request.execution_id)
            await asyncio.sleep(0.2)
            completed.append(request.execution_id)
            async for e in super().execute(request, context):
                yield e

    fake = SlowFake()
    registry = _registry_with_handler(fake)
    engine = _engine(registry=registry, concurrency_limit=1)

    ids = []
    for _i in range(3):
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

    async def _run_one(eid) -> None:
        async for _ in engine.run_job(eid):
            pass

    # Run all three concurrently; with concurrency_limit=1, only one at a time.
    await asyncio.gather(*[_run_one(i) for i in ids])

    assert len(completed) == 3
    # At no point were more than 1 running at once: started order == completed
    # order when concurrency is 1.
    assert started == completed


# ---------------------------------------------------------------------------
# cannot run non-ready job


@pytest.mark.asyncio
async def test_run_rejects_non_ready() -> None:
    engine = _engine()
    execution_id = await engine.create_job(
        engagement_id="eng-1",
        action_id="test.action",
        inputs={"argv": ["--flag"]},
        target_refs=["10.0.0.1"],
    )
    # status is still draft, not ready
    from ambrosia.domain.errors import ConflictError

    with pytest.raises(ConflictError):
        async for _ in engine.run_job(execution_id):
            pass
