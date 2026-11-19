"""Repository and executor protocols used by the application layer.

Repositories return domain objects, never ORM model instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ambrosia.domain.action import ActionAvailability, ActionDefinition

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord, Scope


@runtime_checkable
class EngagementRepository(Protocol):
    def get(self, engagement_id: str) -> Engagement | None: ...  # pragma: no cover
    def create(self, engagement: Engagement) -> Engagement: ...  # pragma: no cover
    def list(self) -> list[Engagement]: ...  # pragma: no cover
    def update(self, engagement: Engagement) -> None: ...  # pragma: no cover


@runtime_checkable
class ScopeRepository(Protocol):
    def get(self, scope_id: str) -> Scope | None: ...  # pragma: no cover
    def create(self, scope: Scope) -> Scope: ...  # pragma: no cover
    def get_for_engagement(self, engagement_id: str) -> Scope | None: ...  # pragma: no cover
    def update(self, scope: Scope) -> None: ...  # pragma: no cover


@runtime_checkable
class ArtifactRepository(Protocol):
    def add(self, artifact: Artifact) -> Artifact: ...  # pragma: no cover
    def list_for_engagement(self, engagement_id: str) -> list[Artifact]: ...  # pragma: no cover
    def get(self, artifact_id: str) -> Artifact | None: ...  # pragma: no cover
    def list_by_target(self, target_ref: str) -> list[Artifact]: ...  # pragma: no cover


@runtime_checkable
class ExecutionRepository(Protocol):
    def add(self, execution: ExecutionRecord) -> ExecutionRecord: ...  # pragma: no cover
    def update(self, execution: ExecutionRecord) -> None: ...  # pragma: no cover
    def list_for_engagement(self, engagement_id: str) -> list[ExecutionRecord]: ...  # pragma: no cover
    def get(self, execution_id: str) -> ExecutionRecord | None: ...  # pragma: no cover
    def add_event(
        self, execution_id: str, kind: str, payload: dict[str, object], sequence: int
    ) -> None: ...  # pragma: no cover


@runtime_checkable
class ActionHandler(Protocol):
    """Handler protocol for executing an action.

    ``ActionExecutionContext`` exposes read-only services only: it must not
    expose the TUI application instance or a raw SQLAlchemy session.
    """

    async def execute(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]: ...  # pragma: no cover


@runtime_checkable
class SecretStore(Protocol):
    """Opaque secret reference resolution. Never returns plaintext by default."""

    async def resolve(self, secret_ref: str) -> object: ...  # pragma: no cover


class ActionRequest:
    """Validated, resolved inputs plus an execution ID."""

    def __init__(
        self,
        *,
        execution_id: str,
        action_id: str,
        inputs: dict[str, object],
        target_refs: list[str] | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.action_id = action_id
        self.inputs = inputs
        self.target_refs = target_refs or []


class ActionExecutionContext:
    """Read-only execution context passed to action handlers."""

    def __init__(
        self,
        *,
        engagement_id: str,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.engagement_id = engagement_id
        self.secret_store = secret_store


class ExecutionEvent:
    """Serializable event emitted during execution."""

    def __init__(
        self,
        *,
        kind: str,
        execution_id: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.kind = kind
        self.execution_id = execution_id
        self.payload = payload or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "execution_id": self.execution_id,
            "payload": self.payload,
        }


__all__ = [
    "EngagementRepository",
    "ScopeRepository",
    "ArtifactRepository",
    "ExecutionRepository",
    "ActionHandler",
    "SecretStore",
    "ActionRequest",
    "ActionExecutionContext",
    "ExecutionEvent",
    "ActionAvailability",
    "ActionDefinition",
]
