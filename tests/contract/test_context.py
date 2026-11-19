"""Contract tests for the engagement-scoped context service."""

from __future__ import annotations

from datetime import datetime, timedelta

from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeExecutionRepository,
    FakeScopeRepository,
)

from ambrosia.artifacts import create_artifact, is_expired
from ambrosia.context import ContextService
from ambrosia.domain.action import ArtifactRequirement
from ambrosia.domain.context import ContextEvent
from ambrosia.domain.models import Engagement, Scope, Target


def _future() -> datetime:
    return datetime.now() + timedelta(days=7)


def _past() -> datetime:
    return datetime.now() - timedelta(days=7)


def _make_service(
    engagement_id: str = "eng-1",
) -> tuple[ContextService, FakeArtifactRepository, FakeExecutionRepository]:
    engagement_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    artifact_repo = FakeArtifactRepository()
    execution_repo = FakeExecutionRepository()
    engagement_repo.create(Engagement(id=engagement_id, name="lab", scope_id="scope-1"))
    scope_repo.create(Scope(id="scope-1", engagement_id=engagement_id, include_hosts=["10.0.0.1"]))
    service = ContextService(
        engagement_id=engagement_id,
        engagement_repository=engagement_repo,
        scope_repository=scope_repo,
        artifact_repository=artifact_repo,
        execution_repository=execution_repo,
    )
    return service, artifact_repo, execution_repo


# ---------------------------------------------------------------------------
# Snapshot namespaces
# ---------------------------------------------------------------------------

def test_snapshot_exposes_all_namespaces() -> None:
    service, _, _ = _make_service()
    target = service.add_target(Target(engagement_id="eng-1", address="dc01.corp.local", kind="domain"))
    artifact = service.create_artifact(
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1"]},
        target_ref=target.id,
    )
    service.derive_fact(
        fact_type="role",
        value={"role": "domain_controller"},
        target_ref=target.id,
        source_artifact_id=artifact.id,
        derived_from=[artifact.id],
    )

    snapshot = service.get_snapshot()
    ns = snapshot.namespaces

    expected = {
        "engagement", "scope", "target", "selected_target", "artifacts",
        "facts", "last_execution", "user",
    }
    assert set(ns.model_dump().keys()) == expected
    assert snapshot.engagement_id == "eng-1"
    assert ns.engagement.get("id") == "eng-1"
    assert ns.scope.get("include_hosts") == ["10.0.0.1"]
    assert target.id in ns.target
    assert artifact.id in ns.artifacts
    assert snapshot.namespaces.facts  # derived fact present


def test_selected_target_namespace() -> None:
    service, _, _ = _make_service()
    target = service.add_target(Target(engagement_id="eng-1", address="dc01.corp.local", kind="domain"))
    service.select_target(target.id)
    snapshot = service.get_snapshot()
    assert target.id in snapshot.namespaces.selected_target


# ---------------------------------------------------------------------------
# Artifacts are queried from the repository, not duplicated in a mutable dict
# ---------------------------------------------------------------------------

def test_service_holds_no_own_artifact_copy() -> None:
    service, artifact_repo, _ = _make_service()
    # The service must not maintain a mutable arbitrary dictionary of artifacts.
    assert not hasattr(service, "_artifacts")
    assert not hasattr(service, "artifacts")

    artifact = service.create_artifact(
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1"]},
        target_ref="target-a",
    )
    # Snapshot artifacts come from the repository.
    snapshot = service.get_snapshot()
    assert artifact.id in snapshot.namespaces.artifacts
    assert snapshot.namespaces.artifacts[artifact.id]["value"]["hostname"] == "dc01"

    # Directly adding to the repository is reflected in the snapshot.
    extra = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "extra"},
        target_ref="target-a",
    )
    artifact_repo.add(extra)
    snapshot2 = service.get_snapshot()
    assert extra.id in snapshot2.namespaces.artifacts


# ---------------------------------------------------------------------------
# Derived facts keep target provenance (no cross-host leakage)
# ---------------------------------------------------------------------------

def test_fact_provenance_and_no_cross_host_leak() -> None:
    service, artifact_repo, _ = _make_service()
    target_a = service.add_target(Target(engagement_id="eng-1", address="10.0.0.1", kind="ip"))
    artifact_a = service.create_artifact(
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1"]},
        target_ref=target_a.id,
    )

    fact = service.derive_fact(
        fact_type="role",
        value={"role": "domain_controller"},
        target_ref=target_a.id,
        source_artifact_id=artifact_a.id,
        derived_from=[artifact_a.id],
    )

    assert fact.target_ref == target_a.id
    assert fact.source_artifact_id == artifact_a.id
    assert fact.derived_from == [artifact_a.id]

    # The fact is about target-a only.
    facts_a = service.facts_for_target(target_a.id)
    assert any(f.id == fact.id for f in facts_a)
    assert service.facts_for_target("other-target") == []

    # Serialized snapshot fact retains provenance.
    snapshot = service.get_snapshot()
    serialized = snapshot.namespaces.facts[fact.id]
    assert serialized["target_ref"] == target_a.id
    assert serialized["source_artifact_id"] == artifact_a.id


# ---------------------------------------------------------------------------
# Target scoping prevents cross-host artifact matches
# ---------------------------------------------------------------------------

def test_match_action_requirements_respects_same_target() -> None:
    service, artifact_repo, _ = _make_service()
    target_a = service.add_target(Target(engagement_id="eng-1", address="10.0.0.1", kind="ip"))
    target_b = service.add_target(Target(engagement_id="eng-1", address="10.0.0.2", kind="ip"))

    svc_a = service.create_artifact(
        type="network.service",
        value={"host_ref": target_a.id, "port": 445, "service_name": "smb"},
        target_ref=target_a.id,
    )

    matched, missing = service.match_action_requirements(
        [ArtifactRequirement(type="network.service", same_target=True)],
        action_target_ref=target_a.id,
    )
    assert svc_a.id in matched
    assert missing == []

    matched_b, missing_b = service.match_action_requirements(
        [ArtifactRequirement(type="network.service", same_target=True)],
        action_target_ref=target_b.id,
    )
    assert svc_a.id not in matched_b
    assert missing_b == ["network.service"]


# ---------------------------------------------------------------------------
# Supersession and expiry behavior
# ---------------------------------------------------------------------------

def test_superseded_and_expired_excluded_from_snapshot() -> None:
    service, artifact_repo, _ = _make_service()
    target = service.add_target(Target(engagement_id="eng-1", address="10.0.0.1", kind="ip"))

    original = service.create_artifact(
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1"]},
        target_ref=target.id,
    )
    replacement = service.create_artifact(
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.2"]},
        target_ref=target.id,
        supersedes=original.id,
    )
    expired = service.create_artifact(
        type="network.host",
        value={"hostname": "old"},
        target_ref=target.id,
        expires_at=_past(),
    )

    snapshot = service.get_snapshot()
    artifact_ids = set(snapshot.namespaces.artifacts.keys())
    assert replacement.id in artifact_ids
    assert original.id not in artifact_ids  # superseded
    assert expired.id not in artifact_ids  # expired

    assert is_expired(expired)


# ---------------------------------------------------------------------------
# Context event serialization
# ---------------------------------------------------------------------------

def test_context_event_serialization_round_trip() -> None:
    event = ContextEvent(
        kind="ArtifactCreated",
        engagement_id="eng-1",
        payload={"artifact_id": "art-1", "type": "network.host"},
    )
    dumped = event.model_dump()
    restored = ContextEvent.model_validate(dumped)
    assert restored.kind == event.kind
    assert restored.engagement_id == event.engagement_id
    assert restored.payload == event.payload

    # Events carry IDs and safe summaries, never secret values.
    assert "secret" not in str(dumped)
    assert "password" not in str(dumped)


def test_service_emits_events_for_target_and_artifact_changes() -> None:
    service, _, _ = _make_service()
    events = []

    def emit(event: ContextEvent) -> None:
        events.append(event)

    service._emit = emit
    target = service.add_target(Target(engagement_id="eng-1", address="10.0.0.1", kind="ip"))
    artifact = service.create_artifact(
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1"]},
        target_ref=target.id,
    )

    kinds = [e.kind for e in events]
    assert "TargetAdded" in kinds
    assert "ArtifactCreated" in kinds

    # Event payloads are safe summaries (IDs only).
    artifact_events = [e for e in events if e.kind == "ArtifactCreated"]
    assert artifact_events[0].payload["artifact_id"] == artifact.id
    assert artifact_events[0].engagement_id == "eng-1"
