"""Shared test fixtures: in-memory implementations of the repository protocols."""

from __future__ import annotations

from ambrosia.domain.models import (
    Artifact,
    Engagement,
    ExecutionRecord,
    Scope,
)
from ambrosia.domain.protocols import (
    ArtifactRepository,
    EngagementRepository,
    ExecutionRepository,
    ScopeRepository,
)


class FakeEngagementRepository(EngagementRepository):
    def __init__(self) -> None:
        self._items: dict[str, Engagement] = {}

    def get(self, engagement_id: str) -> Engagement | None:
        return self._items.get(engagement_id)

    def create(self, engagement: Engagement) -> Engagement:
        self._items[engagement.id] = engagement
        return engagement

    def list(self) -> list[Engagement]:
        return list(self._items.values())

    def update(self, engagement: Engagement) -> None:
        self._items[engagement.id] = engagement


class FakeScopeRepository(ScopeRepository):
    def __init__(self) -> None:
        self._items: dict[str, Scope] = {}

    def get(self, scope_id: str) -> Scope | None:
        return self._items.get(scope_id)

    def create(self, scope: Scope) -> Scope:
        self._items[scope.id] = scope
        return scope

    def get_for_engagement(self, engagement_id: str) -> Scope | None:
        for scope in self._items.values():
            if scope.engagement_id == engagement_id:
                return scope
        return None

    def update(self, scope: Scope) -> None:
        self._items[scope.id] = scope


class FakeArtifactRepository(ArtifactRepository):
    def __init__(self) -> None:
        self._items: dict[str, Artifact] = {}

    def add(self, artifact: Artifact) -> Artifact:
        self._items[artifact.id] = artifact
        return artifact

    def list_for_engagement(self, engagement_id: str) -> list[Artifact]:
        return [a for a in self._items.values() if a.engagement_id == engagement_id]

    def get(self, artifact_id: str) -> Artifact | None:
        return self._items.get(artifact_id)

    def list_by_target(self, target_ref: str) -> list[Artifact]:
        return [a for a in self._items.values() if a.target_ref == target_ref]


class FakeExecutionRepository(ExecutionRepository):
    def __init__(self) -> None:
        self._items: dict[str, ExecutionRecord] = {}
        self._events: dict[str, list[dict[str, object]]] = {}

    def add(self, execution: ExecutionRecord) -> ExecutionRecord:
        self._items[execution.id] = execution
        return execution

    def update(self, execution: ExecutionRecord) -> None:
        self._items[execution.id] = execution

    def list_for_engagement(self, engagement_id: str) -> list[ExecutionRecord]:
        return [e for e in self._items.values() if e.engagement_id == engagement_id]

    def get(self, execution_id: str) -> ExecutionRecord | None:
        return self._items.get(execution_id)

    def add_event(
        self, execution_id: str, kind: str, payload: dict[str, object], sequence: int
    ) -> None:
        self._events.setdefault(execution_id, []).append(
            {"kind": kind, "payload": dict(payload), "sequence": sequence}
        )

    def list_events(self, execution_id: str) -> list[dict[str, object]]:
        return list(self._events.get(execution_id, []))
