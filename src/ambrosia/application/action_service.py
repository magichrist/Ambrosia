"""Application service for actions.

Actions are registered in the action registry (Agent 3). This service exposes
listing, inspection, and availability checking. Availability is computed by the
pure matcher, so the CLI and the TUI see identical results.
"""

from __future__ import annotations

import shutil
from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from ambrosia.application._base import _BaseService
from ambrosia.domain.errors import NotFoundError
from ambrosia.registry.models import (  # noqa: TC001 - constructed at runtime below
    ContextSnapshot,
    PolicySnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ambrosia.domain.action import ActionDefinition
    from ambrosia.domain.protocols import (
        ArtifactRepository as ArtifactRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        EngagementRepository as EngagementRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        ScopeRepository as ScopeRepositoryProtocol,
    )
    from ambrosia.registry import Registry


class ActionDTO(BaseModel):
    """Safe display representation of a registered action definition."""

    id: str
    version: str
    name: str
    description: str
    category: str
    tags: list[str]
    platforms: list[str]
    phase_refs: list[str]
    executor_kind: str
    executor_executable: str | None = None
    effects: list[str]
    risk: str
    approval_required: bool
    timeout_seconds: int
    max_output_bytes: int
    dependencies: list[str]
    scope_fields: list[str]
    required_artifacts: list[str]
    output_artifact_types: list[str]
    parser_refs: list[str]


class ActionListDTO(BaseModel):
    actions: list[ActionDTO]


class ActionCheckDTO(BaseModel):
    """Matcher result for a single action: usable now, and if not, why."""

    action_id: str
    status: str
    reasons: list[str]
    missing_inputs: list[str]
    matched_artifact_ids: list[str]
    required_approval: bool
    allowed: bool  # True when status is "available"


class ActionService(_BaseService):
    def __init__(
        self,
        *,
        registry: Registry,
        session_scope: Callable[[], AbstractContextManager[object | None]] = nullcontext,
        engagement_repo: object = None,
        scope_repo: object = None,
        artifact_repo: object = None,
    ) -> None:
        super().__init__(
            session_scope=session_scope,
            engagement_repo=engagement_repo,
            scope_repo=scope_repo,
            artifact_repo=artifact_repo,
        )
        self._registry = registry

    def list(
        self,
        *,
        category: str | None = None,
        tag: str | None = None,
        platform: str | None = None,
    ) -> ActionListDTO:
        definitions = self._registry.list(
            category=category, tag=tag, platform=platform, enabled_only=True
        )
        return ActionListDTO(actions=[self._dto(d) for d in definitions])

    def info(self, action_id: str) -> ActionDTO:
        definition = self._registry.get(action_id)
        if definition is None:
            raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                f"action {action_id!r} is not registered"
            )
        return self._dto(definition)

    def check(
        self,
        action_id: str,
        *,
        engagement_id: str,
        target_address: str | None = None,
    ) -> ActionCheckDTO:
        """Return availability for ``action_id`` without executing anything.

        Unknown actions raise :class:`~ambrosia.domain.errors.NotFoundError`.
        Blocked/policy results are returned (not raised) so the caller decides
        how to present them; use :meth:`assert_allowed` for run paths.
        """
        snapshot = self._context_snapshot(engagement_id, target_address)
        available_tools = self._available_tools(action_id)
        policy = self._policy_snapshot(engagement_id)

        from ambrosia.registry import AvailabilityMatcher

        matcher = AvailabilityMatcher(self._registry)
        availability = matcher.evaluate(
            action_id,
            replace(snapshot, available_tools=available_tools),
            policy,
        )
        return ActionCheckDTO(
            action_id=availability.action_id,
            status=availability.status,
            reasons=list(availability.reasons),
            missing_inputs=list(availability.missing_inputs),
            matched_artifact_ids=list(availability.matched_artifact_ids),
            required_approval=availability.required_approval,
            allowed=availability.status == "available",
        )

    def assert_allowed(
        self,
        action_id: str,
        *,
        engagement_id: str,
        target_address: str | None = None,
        authorization_reference: str | None = None,
    ) -> None:
        """Raise a typed domain error if the action cannot run.

        Used by execution paths (preset run) so the CLI can never bypass
        policy validation.
        """
        from ambrosia.application.policy_gateway import PolicyGateway

        gateway = PolicyGateway(
            session_scope=self._session_scope,
            registry=self._registry,
            engagement_repository=cast(
                "EngagementRepositoryProtocol",
                self._repos.get("engagement_repo"),
            ),
            scope_repository=cast("ScopeRepositoryProtocol", self._repos.get("scope_repo")),
            artifact_repository=cast(
                "ArtifactRepositoryProtocol", self._repos.get("artifact_repo")
            ),
        )
        gateway.check_action(
            action_id=action_id,
            engagement_id=engagement_id,
            target_address=target_address,
            available_tools=self._available_tools(action_id),
            authorization_reference=authorization_reference,
        )

    # ------------------------------------------------------------------ internals

    def _context_snapshot(
        self,
        engagement_id: str,
        target_address: str | None = None,
    ) -> ContextSnapshot:
        with self._session() as session:
            artifact_repo = cast(
                "ArtifactRepositoryProtocol",
                self._repo("artifact_repo", session),
            )
            scope_repo = cast("ScopeRepositoryProtocol", self._repo("scope_repo", session))
            artifacts = tuple(artifact_repo.list_for_engagement(engagement_id))
            scope = scope_repo.get_for_engagement(engagement_id)
        selected_target: dict[str, object] | None = None
        if target_address is not None:
            selected_target = {"address": target_address}
        return ContextSnapshot(
            engagement_id=engagement_id,
            selected_target=selected_target,
            scope_targets=tuple(
                (scope.include_hosts or [])
                + (scope.include_cidrs or [])
                + (scope.include_domains or [])
            )
            if scope is not None
            else (),
            artifacts=artifacts,
            inputs={},
            available_tools=frozenset(),
            platform="current",
        )

    def _policy_snapshot(self, engagement_id: str) -> PolicySnapshot:
        with self._session() as session:
            scope_repo = cast("ScopeRepositoryProtocol", self._repo("scope_repo", session))
            scope = scope_repo.get_for_engagement(engagement_id)
        if scope is None:
            from ambrosia.domain.models import Scope

            scope = Scope(engagement_id=engagement_id)
        return PolicySnapshot.from_scope(scope)

    def _available_tools(self, action_id: str) -> frozenset[str]:
        """Metadata-only tool availability: executables found on PATH.

        No tool is executed here; this mirrors the registry's dependency
        declarations so ``missing_dependency`` is reported honestly.
        """
        definition = self._registry.get(action_id)
        if definition is None:
            return frozenset()
        available: set[str] = set()
        for dependency in definition.dependencies:
            if shutil.which(dependency.name) is not None:
                available.add(dependency.name)
        return frozenset(available)

    @staticmethod
    def _dto(definition: ActionDefinition) -> ActionDTO:
        return ActionDTO(
            id=definition.id,
            version=definition.version,
            name=definition.name,
            description=definition.description,
            category=definition.category,
            tags=list(definition.tags),
            platforms=list(definition.platforms),
            phase_refs=list(definition.phase_refs),
            executor_kind=definition.executor.kind,
            executor_executable=definition.executor.executable,
            effects=list(definition.effects),
            risk=definition.risk,
            approval_required=definition.approval_required,
            timeout_seconds=definition.timeout_seconds,
            max_output_bytes=definition.max_output_bytes,
            dependencies=[dep.name for dep in definition.dependencies],
            scope_fields=list(definition.scope_fields),
            required_artifacts=[req.type for req in definition.required_artifacts],
            output_artifact_types=list(definition.output_artifact_types),
            parser_refs=list(definition.parser_refs),
        )


__all__ = ["ActionDTO", "ActionListDTO", "ActionCheckDTO", "ActionService"]
