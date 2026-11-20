# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for Windows assessment pack action handlers.

Handlers are exercised with a stub executor and static Nmap XML fixtures, so no
live target or Nmap installation is required. Tests verify that tool output
becomes typed artifact drafts and that handlers never start a real subprocess.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from ambrosia.artifacts.lifecycle import create_artifact
from ambrosia.artifacts.models import ServiceArtifact
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionHandler,
    ActionRequest,
    ExecutionEvent,
)
from ambrosia.packs.windows_assessment import handlers

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "packs" / "windows_assessment"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class _StubExecutor:
    """Stub executor that returns canned stdout without starting a process."""

    def __init__(self, stdout: str = "", exit_code: int = 0) -> None:
        self.stdout = stdout
        self.exit_code = exit_code
        self.calls: list[tuple[ActionRequest, ActionExecutionContext]] = []

    async def execute(
        self, request: ActionRequest, context: ActionExecutionContext
    ) -> AsyncIterator[ExecutionEvent]:
        self.calls.append((request, context))
        execution_id = request.execution_id
        yield ExecutionEvent(
            kind="ProgressEvent",
            execution_id=execution_id,
            payload={"message": "stub started"},
        )
        yield ExecutionEvent(
            kind="OutputChunkEvent",
            execution_id=execution_id,
            payload={"stream": "stdout", "text": self.stdout},
        )
        yield ExecutionEvent(
            kind="CompletedEvent",
            execution_id=execution_id,
            payload={
                "summary": {
                    "exit_code": self.exit_code,
                    "stdout": self.stdout,
                    "stderr": "",
                    "duration_seconds": 0.0,
                }
            },
        )


def _context() -> ActionExecutionContext:
    return ActionExecutionContext(engagement_id="eng-1")


def _request(action_id: str, **inputs: object) -> ActionRequest:
    return ActionRequest(
        execution_id="exec-1",
        action_id=action_id,
        inputs=dict(inputs),
    )


async def _collect(
    handler: ActionHandler,
    request: ActionRequest,
    context: ActionExecutionContext,
) -> list[ExecutionEvent]:
    return [e async for e in handler.execute(request, context)]


def _artifact_drafts(events: list[ExecutionEvent]) -> list[dict[str, object]]:
    return [
        e.payload
        for e in events
        if e.kind == "ArtifactProducedEvent" and isinstance(e.payload, dict)
    ]


# ---------------------------------------------------------------------------
# network.nmap.service_discovery
# ---------------------------------------------------------------------------


def test_service_discovery_produces_typed_service_artifacts() -> None:
    executor = _StubExecutor(stdout=_fixture("nmap_service_discovery.xml"))
    handler = handlers.NmapServiceDiscoveryHandler(executor=executor)
    events = asyncio.run(
        _collect(
            handler,
            _request("network.nmap.service_discovery", target="10.0.0.10"),
            _context(),
        )
    )

    drafts = _artifact_drafts(events)
    assert len(drafts) == 4  # 445, 80, 3389, 5985 are open; 135 is filtered
    ports = {d["value"]["port"] for d in drafts}
    assert ports == {445, 80, 3389, 5985}

    # Every draft is a valid typed network.service artifact payload.
    smb = next(d for d in drafts if d["value"]["port"] == 445)
    artifact = create_artifact(
        engagement_id="eng-1",
        type="network.service",
        value=smb["value"],
        target_ref=smb["target_ref"],
        source_id="network.nmap.service_discovery",
    )
    assert isinstance(artifact, ServiceArtifact)
    assert artifact.value.service_name == "microsoft-ds"
    assert artifact.value.port == 445
    assert artifact.value.state == "open"

    # The stub executor was invoked with an argv array, never a shell string.
    assert executor.calls
    argv = executor.calls[0][0].inputs["argv"]
    assert isinstance(argv, list)
    assert argv[0] == "-oX"
    assert "10.0.0.10" in argv


def test_service_discovery_empty_fixture_produces_no_artifacts() -> None:
    executor = _StubExecutor(stdout=_fixture("nmap_empty.xml"))
    handler = handlers.NmapServiceDiscoveryHandler(executor=executor)
    events = asyncio.run(
        _collect(
            handler,
            _request("network.nmap.service_discovery", target="10.0.0.99"),
            _context(),
        )
    )
    assert _artifact_drafts(events) == []
    assert any(e.kind == "CompletedEvent" for e in events)


def test_service_discovery_malformed_output_fails() -> None:
    executor = _StubExecutor(stdout=_fixture("nmap_malformed.xml"))
    handler = handlers.NmapServiceDiscoveryHandler(executor=executor)
    events = asyncio.run(
        _collect(
            handler,
            _request("network.nmap.service_discovery", target="10.0.0.1"),
            _context(),
        )
    )
    failed = [e for e in events if e.kind == "FailedEvent"]
    assert len(failed) == 1
    assert failed[0].payload["code"] == "execution_error"


# ---------------------------------------------------------------------------
# windows.smb.configuration_audit
# ---------------------------------------------------------------------------


def test_smb_audit_produces_domain_and_role_artifacts() -> None:
    executor = _StubExecutor(stdout=_fixture("nmap_smb_only.xml"))
    handler = handlers.SmbConfigurationAuditHandler(executor=executor)
    events = asyncio.run(
        _collect(
            handler,
            _request("windows.smb.configuration_audit", target="10.0.0.20", port=445),
            _context(),
        )
    )

    drafts = _artifact_drafts(events)
    types = {d["type"] for d in drafts}
    assert "windows.domain" in types
    assert "windows.host_role" in types
    assert "observation" in types

    domain = next(d for d in drafts if d["type"] == "windows.domain")
    assert domain["value"]["name"] == "CONTOSO.LOCAL"
    assert domain["value"]["domain_controller"] == "10.0.0.20"

    role = next(d for d in drafts if d["type"] == "windows.host_role")
    assert role["value"]["host_ref"] == "10.0.0.20"
    assert role["value"]["role"] == "domain_controller"


def test_smb_audit_empty_fixture_produces_no_artifacts() -> None:
    executor = _StubExecutor(stdout=_fixture("nmap_empty.xml"))
    handler = handlers.SmbConfigurationAuditHandler(executor=executor)
    events = asyncio.run(
        _collect(
            handler,
            _request("windows.smb.configuration_audit", target="10.0.0.99", port=445),
            _context(),
        )
    )
    assert _artifact_drafts(events) == []


# ---------------------------------------------------------------------------
# Handler never starts a real process
# ---------------------------------------------------------------------------


def test_handler_uses_injected_executor_only() -> None:
    executor = _StubExecutor(stdout=_fixture("nmap_service_discovery.xml"))
    handler = handlers.NmapServiceDiscoveryHandler(executor=executor)
    asyncio.run(
        _collect(
            handler,
            _request("network.nmap.service_discovery", target="10.0.0.10"),
            _context(),
        )
    )
    # The stub executor recorded the call; no real subprocess was started.
    assert len(executor.calls) == 1
    assert executor.calls[0][0].inputs["argv"][-1] == "10.0.0.10"
