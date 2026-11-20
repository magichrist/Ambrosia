# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Contract tests for the Windows assessment pack: end-to-end artifact flow.

Verifies that tool output becomes typed artifacts and that the resulting
artifacts change the suggested action list. Uses a stub executor and static
fixtures; no live target or Nmap installation is required.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from ambrosia.artifacts.lifecycle import create_artifact
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionRequest,
    ExecutionEvent,
)
from ambrosia.packs.windows_assessment import handlers, register_pack
from ambrosia.registry import (
    AvailabilityMatcher,
    ContextSnapshot,
    PolicySnapshot,
    Registry,
)

_PLATFORM_MAP = {"darwin": "darwin", "linux": "linux", "win32": "windows"}


def _platform() -> str:
    return _PLATFORM_MAP.get(sys.platform, sys.platform)


FIXTURES = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "packs" / "windows_assessment"
)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class _StubExecutor:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.calls: list[tuple[ActionRequest, ActionExecutionContext]] = []

    async def execute(
        self, request: ActionRequest, context: ActionExecutionContext
    ) -> AsyncIterator[ExecutionEvent]:
        self.calls.append((request, context))
        execution_id = request.execution_id
        yield ExecutionEvent(kind="ProgressEvent", execution_id=execution_id, payload={})
        yield ExecutionEvent(
            kind="OutputChunkEvent",
            execution_id=execution_id,
            payload={"stream": "stdout", "text": self.stdout},
        )
        yield ExecutionEvent(
            kind="CompletedEvent",
            execution_id=execution_id,
            payload={
                "summary": {"exit_code": 0, "stdout": self.stdout, "stderr": "", "duration_seconds": 0.0}
            },
        )


def _context() -> ActionExecutionContext:
    return ActionExecutionContext(engagement_id="eng-1")


def _registry_with_pack() -> tuple[Registry, _StubExecutor]:
    stub = _StubExecutor(stdout=_fixture("nmap_service_discovery.xml"))
    registry = Registry()
    register_pack(registry, executor=stub)
    return registry, stub


def _policy() -> PolicySnapshot:
    return PolicySnapshot(
        allowed_effects=frozenset({"local_read", "network_observe"}),
        require_approval_for=frozenset(
            {"local_write", "remote_change", "authentication", "credential_access"}
        ),
        include_hosts=("10.0.0.10",),
    )


def _context_with(
    artifacts: tuple = (), inputs: dict[str, object] | None = None
) -> ContextSnapshot:
    return ContextSnapshot(
        engagement_id="eng-1",
        selected_target={"address": "10.0.0.10"},
        artifacts=tuple(artifacts),
        inputs=dict(inputs or {"target": "10.0.0.10"}),
        available_tools=frozenset({"nmap"}),
        platform=_platform(),
    )


async def _run_discovery(stub: _StubExecutor) -> list[dict[str, object]]:
    handler = handlers.NmapServiceDiscoveryHandler(executor=stub)
    request = ActionRequest(
        execution_id="exec-1",
        action_id="network.nmap.service_discovery",
        inputs={"target": "10.0.0.10", "ports": "80,443,445,3389,5985"},
    )
    events = [e async for e in handler.execute(request, _context())]
    return [
        e.payload
        for e in events
        if e.kind == "ArtifactProducedEvent" and isinstance(e.payload, dict)
    ]


def test_pack_loads_and_matches_before_and_after_artifacts() -> None:
    registry, stub = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)

    # Before discovery: the SMB audit action cannot apply (missing artifact).
    before = matcher.evaluate("windows.smb.configuration_audit", _context_with(), _policy())
    assert before.status == "not_applicable"
    assert any("missing required artifact" in r for r in before.reasons)

    # Discovery runs end-to-end with the stub executor and yields typed
    # artifact drafts.
    drafts = asyncio.run(_run_discovery(stub))
    assert len(drafts) == 4
    assert all(d["type"] == "network.service" for d in drafts)

    # Tool output becomes typed artifacts persisted to the engagement.
    artifacts = [
        create_artifact(
            engagement_id="eng-1",
            type=d["type"],
            value=d["value"],
            source_id=d["source_id"],
            source_execution_id=d["source_execution_id"],
            target_ref=d["target_ref"],
            confidence=d.get("confidence"),
            sensitivity=d.get("sensitivity"),
            metadata=d.get("metadata", {}),
        )
        for d in drafts
    ]
    smb_artifacts = [a for a in artifacts if a.value.service_name == "microsoft-ds"]
    assert len(smb_artifacts) == 1

    # After discovery: the SMB audit action becomes applicable on the same
    # target — resulting artifacts change the suggested action list.
    after = matcher.evaluate(
        "windows.smb.configuration_audit",
        _context_with(artifacts=tuple(artifacts)),
        _policy(),
    )
    assert after.status == "available", after.reasons
    assert smb_artifacts[0].id in after.matched_artifact_ids

    # The stub executor was used; no real Nmap process was started.
    assert stub.calls
    assert stub.calls[0][0].inputs["argv"][-1] == "10.0.0.10"


def test_discovers_all_services_and_related_actions_are_suggested() -> None:
    registry, stub = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)

    drafts = asyncio.run(_run_discovery(stub))
    artifacts = [
        create_artifact(
            engagement_id="eng-1",
            type=d["type"],
            value=d["value"],
            source_id=d["source_id"],
            source_execution_id=d["source_execution_id"],
            target_ref=d["target_ref"],
            confidence=d.get("confidence"),
            sensitivity=d.get("sensitivity"),
            metadata=d.get("metadata", {}),
        )
        for d in drafts
    ]
    context = _context_with(artifacts=tuple(artifacts))

    # Each discovered service family surfaces its corresponding action on the
    # same target.
    for action_id in (
        "windows.smb.configuration_audit",
        "windows.http.method_observation",
        "windows.rdp.exposure_observation",
        "windows.winrm.exposure_observation",
    ):
        avail = matcher.evaluate(action_id, context, _policy())
        assert avail.status == "available", f"{action_id}: {avail.reasons}"

    # LDAP was not discovered, so its action stays not_applicable.
    ldap = matcher.evaluate("windows.ldap.domain_inventory", context, _policy())
    assert ldap.status == "not_applicable"


@pytest.mark.parametrize(
    "action_id",
    [
        "windows.smb.configuration_audit",
        "windows.http.method_observation",
        "windows.rdp.exposure_observation",
        "windows.winrm.exposure_observation",
    ],
)
def test_service_actions_refuse_out_of_scope_target(action_id: str) -> None:
    registry, _ = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)

    context = ContextSnapshot(
        engagement_id="eng-1",
        selected_target={"address": "99.99.99.99"},
        artifacts=(),
        inputs={"target": "99.99.99.99"},
        available_tools=frozenset({"nmap"}),
        platform=_platform(),
    )
    avail = matcher.evaluate(action_id, context, _policy())
    assert avail.status == "blocked"
    assert any("blocked by scope" in r for r in avail.reasons)


def test_network_action_missing_dependency_without_nmap() -> None:
    registry, _ = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)

    # nmap not available as a local tool (metadata check, never executed).
    context = ContextSnapshot(
        engagement_id="eng-1",
        selected_target={"address": "10.0.0.10"},
        artifacts=(),
        inputs={"target": "10.0.0.10"},
        available_tools=frozenset(),
        platform=_platform(),
    )
    avail = matcher.evaluate("network.nmap.service_discovery", context, _policy())
    assert avail.status == "missing_dependency"
    assert any("nmap" in r for r in avail.reasons)
