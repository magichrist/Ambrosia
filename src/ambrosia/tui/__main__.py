"""Run the Ambrosia TUI with an in-memory service stack (demo / dev entry point).

``python -m ambrosia.tui`` launches the adaptive Textual workspace backed by
in-memory fakes so it works without a configured database. Production wiring
(Storage-backed repositories) is assembled by the integrator and passed to
:func:`ambrosia.tui.app.build_app`.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Literal

from ambrosia.actions.builtins import register_builtins
from ambrosia.application import ApplicationServices
from ambrosia.domain.models import (
    Artifact,
    Engagement,
    ExecutionRecord,
    Scope,
    Target,
)
from ambrosia.engine.engine import JobEngine
from ambrosia.policy.engine import PolicyEngine
from ambrosia.registry import Registry
from ambrosia.tui.app import build_app
from ambrosia.tui.services import TUIServiceAdapter


class _FakeEngagementRepository:
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


class _FakeScopeRepository:
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


class _FakeTargetRepository:
    def __init__(self) -> None:
        self._items: dict[str, Target] = {}

    def get(self, target_id: str) -> Target | None:
        return self._items.get(target_id)

    def create(
        self,
        *,
        engagement_id: str,
        address: str,
        target_type: Literal["host", "ip", "domain"] = "host",
        hostname: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
    ) -> Target:
        target = Target(
            engagement_id=engagement_id,
            address=address,
            kind=target_type,
        )
        self._items[target.id] = target
        return target

    def list_for_engagement(self, engagement_id: str) -> list[Target]:
        return [t for t in self._items.values() if t.engagement_id == engagement_id]


class _FakeArtifactRepository:
    def __init__(self) -> None:
        self._items: dict[str, Artifact] = {}

    def add(self, artifact: Artifact) -> Artifact:
        self._items[artifact.id] = artifact
        return artifact

    def list_for_engagement(self, engagement_id: str) -> list[Artifact]:
        return [a for a in self._items.values() if a.engagement_id == engagement_id]

    def list_by_target(self, target_ref: str) -> list[Artifact]:
        return [a for a in self._items.values() if a.target_ref == target_ref]

    def get(self, artifact_id: str) -> Artifact | None:
        return self._items.get(artifact_id)


class _FakeExecutionRepository:
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


def main() -> None:
    registry = Registry()
    register_builtins(registry)

    engagement_repo = _FakeEngagementRepository()
    scope_repo = _FakeScopeRepository()
    target_repo = _FakeTargetRepository()
    artifact_repo = _FakeArtifactRepository()
    execution_repo = _FakeExecutionRepository()

    # Seed one demo engagement so the TUI opens into a real context.
    engagement_repo.create(
        Engagement(id="eng-demo", name="demo-lab", description="demo engagement")
    )
    scope_repo.create(
        Scope(
            id="scope-demo",
            engagement_id="eng-demo",
            include_hosts=["127.0.0.1"],
            allowed_effects={"local_read", "network_observe"},
        )
    )

    services = ApplicationServices(
        session_scope=nullcontext,
        registry=registry,
        engagement_repo=engagement_repo,
        scope_repo=scope_repo,
        artifact_repo=artifact_repo,
        execution_repo=execution_repo,
        target_repo=target_repo,
    )
    engine = JobEngine(
        registry=registry,
        execution_repository=execution_repo,
        policy_engine=PolicyEngine(),
    )
    adapter = TUIServiceAdapter(
        services=services,
        engine=engine,
        execution_repo=execution_repo,
        artifact_repo=artifact_repo,
    )
    build_app(adapter).run()


if __name__ == "__main__":
    main()
