"""Engagement-scoped context service.

Queries repositories through protocols (never SQLAlchemy directly) and does
not duplicate every artifact in a mutable arbitrary dictionary. Artifacts are
read from the :class:`ambrosia.domain.protocols.ArtifactRepository` at snapshot
time. Derived facts and the target registry are maintained by the service
itself (they are derived context state, not a copy of the artifact store).

Emits :class:`ambrosia.domain.context.ContextEvent` instances for target,
artifact, and execution changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ambrosia.artifacts.lifecycle import (
    active_artifacts,
    create_artifact,
    is_expired,
    match_required_artifacts,
    superseded_ids,
)
from ambrosia.context.models import ContextSnapshot, Fact
from ambrosia.domain.context import ContextEvent, ContextNamespace

if TYPE_CHECKING:
    from collections.abc import Callable

    from ambrosia.domain.action import ArtifactRequirement
    from ambrosia.domain.models import (
        Artifact,
        Engagement,
        ExecutionRecord,
        Scope,
        Target,
    )
    from ambrosia.domain.protocols import (
        ArtifactRepository,
        EngagementRepository,
        ExecutionRepository,
        ScopeRepository,
    )


class ContextService:
    """Engagement-scoped context view built from repository protocols."""

    def __init__(
        self,
        *,
        engagement_id: str,
        engagement_repository: EngagementRepository,
        scope_repository: ScopeRepository,
        artifact_repository: ArtifactRepository,
        execution_repository: ExecutionRepository,
        emit: Callable[[ContextEvent], None] | None = None,
    ) -> None:
        self.engagement_id = engagement_id
        self._engagement_repository = engagement_repository
        self._scope_repository = scope_repository
        self._artifact_repository = artifact_repository
        self._execution_repository = execution_repository
        self._emit = emit or (lambda _event: None)

        # Derived context state (not a copy of the artifact store).
        self._targets: dict[str, Target] = {}
        self._facts: dict[str, Fact] = {}
        self._selected_target: str | None = None
        self._events: list[ContextEvent] = []
        self._snapshot_sequence = 0

    # ------------------------------------------------------------------
    # Repository reads (delegated to protocols)
    # ------------------------------------------------------------------

    def get_engagement(self) -> Engagement | None:
        return self._engagement_repository.get(self.engagement_id)

    def get_scope(self) -> Scope | None:
        engagement = self.get_engagement()
        if engagement is None or engagement.scope_id is None:
            return None
        return self._scope_repository.get_for_engagement(self.engagement_id)

    def list_artifacts(self) -> list[Artifact]:
        return self._artifact_repository.list_for_engagement(self.engagement_id)

    def list_executions(self) -> list[ExecutionRecord]:
        return self._execution_repository.list_for_engagement(self.engagement_id)

    # ------------------------------------------------------------------
    # Targets
    # ------------------------------------------------------------------

    def add_target(self, target: Target) -> Target:
        """Register a target for this engagement and emit TargetAdded."""
        if target.engagement_id != self.engagement_id:
            message = "target engagement_id does not match this context"
            raise ValueError(message)
        self._targets[target.id] = target
        self._record("TargetAdded", {"target_id": target.id, "address": target.address})
        return target

    def get_target(self, target_id: str) -> Target | None:
        return self._targets.get(target_id)

    def list_targets(self) -> list[Target]:
        return list(self._targets.values())

    def select_target(self, target_ref: str | None) -> None:
        self._selected_target = target_ref
        self._record(
            "TargetAdded" if target_ref is not None else "ScopeChanged",
            {"selected_target": target_ref},
        )

    def get_selected_target(self) -> str | None:
        return self._selected_target

    # ------------------------------------------------------------------
    # Artifacts (creation goes through the factory; persistence via repo)
    # ------------------------------------------------------------------

    def create_artifact(
        self,
        *,
        type: str,
        value: dict[str, object],
        source_kind: str = "operator",
        source_id: str | None = None,
        source_execution_id: str | None = None,
        target_ref: str | None = None,
        confidence: float | None = None,
        sensitivity: str = "internal",
        secret_ref: str | None = None,
        scope_binding: dict[str, object] | None = None,
        supersedes: str | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Artifact:
        """Create a validated artifact, persist it, and emit ArtifactCreated."""
        artifact = create_artifact(
            engagement_id=self.engagement_id,
            type=type,
            value=value,
            source_kind=source_kind,  # type: ignore[arg-type]
            source_id=source_id,
            source_execution_id=source_execution_id,
            target_ref=target_ref,
            confidence=confidence,
            sensitivity=sensitivity,  # type: ignore[arg-type]
            secret_ref=secret_ref,
            scope_binding=scope_binding,
            supersedes=supersedes,
            expires_at=expires_at,
            metadata=metadata,
        )
        self._artifact_repository.add(artifact)
        self._record(
            "ArtifactCreated",
            {
                "artifact_id": artifact.id,
                "type": artifact.type,
                "target_ref": artifact.target_ref,
            },
        )
        return artifact

    def supersede_artifact(
        self, original_id: str, replacement: Artifact
    ) -> Artifact:
        """Persist a replacement artifact that supersedes ``original_id``."""
        if replacement.supersedes is not None and replacement.supersedes != original_id:
            message = "replacement supersedes field must match original_id"
            raise ValueError(message)
        replacement.supersedes = original_id
        self._artifact_repository.add(replacement)
        self._record(
            "ArtifactSuperseded",
            {
                "superseded_artifact_id": original_id,
                "replacement_artifact_id": replacement.id,
            },
        )
        return replacement

    # ------------------------------------------------------------------
    # Derived facts (provenance-aware)
    # ------------------------------------------------------------------

    def derive_fact(
        self,
        *,
        fact_type: str,
        value: dict[str, object],
        target_ref: str | None = None,
        source_artifact_id: str | None = None,
        derived_from: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> Fact:
        """Create a derived fact bound to a target and source artifact."""
        if source_artifact_id is None and not derived_from:
            message = "a fact must cite at least one source artifact"
            raise ValueError(message)
        fact = Fact(
            engagement_id=self.engagement_id,
            target_ref=target_ref,
            source_artifact_id=source_artifact_id,
            fact_type=fact_type,
            value=value,
            derived_from=derived_from or [],
            expires_at=expires_at,
        )
        self._facts[fact.id] = fact
        return fact

    def get_fact(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def list_facts(self) -> list[Fact]:
        return list(self._facts.values())

    def facts_for_target(self, target_ref: str) -> list[Fact]:
        """Return facts bound to the given target (no cross-host leakage)."""
        return [f for f in self._facts.values() if f.target_ref == target_ref]

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> ContextSnapshot:
        """Build an engagement-scoped context snapshot from repositories."""
        self._snapshot_sequence += 1

        engagement = self.get_engagement()
        scope = self.get_scope()
        artifacts = self.list_artifacts()
        executions = self.list_executions()

        namespaces = self._build_namespaces(
            engagement=engagement,
            scope=scope,
            artifacts=artifacts,
            executions=executions,
        )

        return ContextSnapshot(
            engagement_id=self.engagement_id,
            namespaces=namespaces,
            sequence=self._snapshot_sequence,
        )

    def _build_namespaces(
        self,
        *,
        engagement: Engagement | None,
        scope: Scope | None,
        artifacts: list[Artifact],
        executions: list[ExecutionRecord],
    ) -> ContextNamespace:
        active = active_artifacts(artifacts)

        engagement_ns: dict[str, object] = {}
        if engagement is not None:
            engagement_ns = engagement.model_dump()

        scope_ns: dict[str, object] = {}
        if scope is not None:
            scope_ns = scope.model_dump()

        target_ns: dict[str, object] = {
            target.id: target.model_dump() for target in self._targets.values()
        }

        selected_target_ns: dict[str, object] = {}
        if self._selected_target is not None:
            target = self._targets.get(self._selected_target)
            if target is not None:
                selected_target_ns = {self._selected_target: target.model_dump()}

        artifacts_ns: dict[str, object] = {
            artifact.id: artifact.model_dump() for artifact in active
        }

        facts_ns: dict[str, object] = {
            fact.id: fact.model_dump() for fact in self._facts.values()
        }

        last_execution_ns: dict[str, object] = {}
        if executions:
            latest = max(
                executions,
                key=lambda e: e.started_at or e.finished_at or datetime.min,
            )
            last_execution_ns = latest.model_dump()

        return ContextNamespace(
            engagement=engagement_ns,
            scope=scope_ns,
            target=target_ns,
            selected_target=selected_target_ns,
            artifacts=artifacts_ns,
            facts=facts_ns,
            last_execution=last_execution_ns,
            user={},
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _record(self, kind: str, payload: dict[str, object]) -> None:
        event = ContextEvent(
            kind=kind,  # type: ignore[arg-type]
            engagement_id=self.engagement_id,
            payload=payload,
        )
        self._events.append(event)
        self._emit(event)

    def drain_events(self) -> list[ContextEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    # ------------------------------------------------------------------
    # Pure matching helpers (exposed for the action matcher)
    # ------------------------------------------------------------------

    def match_action_requirements(
        self,
        requirements: list[ArtifactRequirement],
        action_target_ref: str | None = None,
    ) -> tuple[list[str], list[str]]:
        """Pure match of active artifacts against action requirements.

        Artifacts from another host never satisfy a same-target requirement
        unless the action explicitly allows cross-target use.
        """
        return match_required_artifacts(
            active_artifacts(self.list_artifacts()),
            requirements,
            action_target_ref=action_target_ref,
        )

    def is_expired(self, artifact: Artifact) -> bool:
        return is_expired(artifact)

    def superseded_artifact_ids(self) -> set[str]:
        return superseded_ids(self.list_artifacts())
