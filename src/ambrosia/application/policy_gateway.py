"""Policy integration point for application services.

All execution paths (CLI and TUI) must route policy decisions through the same
gateway so the CLI can never bypass policy validation.

This module is a *temporary* fallback: it reuses the pure availability matcher
from ``ambrosia.registry`` (Agent 3) plus the engagement scope as the policy
snapshot. When Agent 5's ``ambrosia.policy`` engine is integrated, this gateway
should delegate to it; the service interface (`check_action`) stays unchanged.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from ambrosia.application._base import _BaseService
from ambrosia.domain.errors import NotFoundError, ScopeViolationError
from ambrosia.registry import AvailabilityMatcher, PolicySnapshot, Registry
from ambrosia.registry.models import ContextSnapshot as RegistryContextSnapshot

if TYPE_CHECKING:
    from ambrosia.domain.models import Scope
    from ambrosia.domain.protocols import (
        ArtifactRepository as ArtifactRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        EngagementRepository as EngagementRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        ScopeRepository as ScopeRepositoryProtocol,
    )


class PolicyGateway(_BaseService):
    """Checks whether an action may run in the current engagement context.

    Raises typed domain errors so callers (CLI, TUI) can map them to exit
    codes without inspecting internals:

    * :class:`~ambrosia.domain.errors.NotFoundError` — unknown action or engagement.
    * :class:`~ambrosia.domain.errors.ScopeViolationError` — target outside scope
      or no scope defined for the engagement.
    * :class:`~ambrosia.domain.errors.PolicyBlockedError` — effect not allowed or
      approval required.
    * :class:`~ambrosia.domain.errors.MissingDependencyError` — a declared local
      dependency is unavailable.
    """

    def __init__(
        self,
        *,
        session_scope: Callable[[], AbstractContextManager[object | None]] = nullcontext,
        registry: Registry,
        engagement_repository: EngagementRepositoryProtocol | None = None,
        scope_repository: ScopeRepositoryProtocol | None = None,
        artifact_repository: object = None,
    ) -> None:
        super().__init__(
            session_scope=session_scope,
            engagement_repo=engagement_repository,
            scope_repo=scope_repository,
            artifact_repo=artifact_repository,
        )
        self._registry = registry
        self._matcher = AvailabilityMatcher(registry)

    # ------------------------------------------------------------------ public

    def check_action(
        self,
        *,
        action_id: str,
        engagement_id: str,
        target_address: str | None = None,
        available_tools: frozenset[str] = frozenset(),
        authorization_reference: str | None = None,
    ) -> object:  # ActionAvailability (imported lazily to avoid a cycle)
        """Return the availability of ``action_id`` for the engagement.

        Raises typed domain errors on policy/scope blocks instead of returning
        a ``blocked`` availability, so CLI and TUI cannot forget to handle them.
        """

        definition = self._registry.get(action_id)
        if definition is None:
            raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                f"action {action_id!r} is not registered"
            )

        # High-impact actions need an explicit per-run authorization before any
        # other policy check or process start.
        from ambrosia.policy.authorization import AuthorizationService  # noqa: PLC0415

        AuthorizationService().require_reference(definition, authorization_reference)

        with self._session() as session:
            scope = self._scope_for(session, engagement_id)
            if scope is None and (definition.scope_fields or definition.effects):
                raise ScopeViolationError(  # noqa: TRY003 - operator-facing message
                    "no scope is defined for this engagement; action requires scope authorization",
                    details={"action_id": action_id, "engagement_id": engagement_id},
                )

            selected_target: dict[str, object] | None = None
            if target_address is not None:
                selected_target = {"address": target_address}

            artifact_repo = cast(  # noqa: TC001
                "ArtifactRepositoryProtocol", self._repo("artifact_repo", session)
            )
            snapshot = RegistryContextSnapshot(
                engagement_id=engagement_id,
                selected_target=selected_target,
                scope_targets=self._scope_targets(scope),
                artifacts=tuple(artifact_repo.list_for_engagement(engagement_id)),
                inputs={},
                available_tools=available_tools,
                platform="current",
            )
            policy = PolicySnapshot.from_scope(scope) if scope is not None else PolicySnapshot()

        availability = self._matcher.evaluate(action_id, snapshot, policy)
        self._raise_on_blocked(availability, action_id, engagement_id)
        return availability

    # ------------------------------------------------------------------ internals

    def _scope_for(self, session: object | None, engagement_id: str) -> Scope | None:
        engagement_repo = cast(  # noqa: TC001
            "EngagementRepositoryProtocol", self._repo("engagement_repo", session)
        )
        engagement = engagement_repo.get(engagement_id)
        if engagement is None:
            raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                f"engagement {engagement_id!r} not found"
            )
        if engagement.scope_id is None:
            return None
        scope_repo = cast(  # noqa: TC001
            "ScopeRepositoryProtocol", self._repo("scope_repo", session)
        )
        return scope_repo.get_for_engagement(engagement_id)

    @staticmethod
    def _scope_targets(scope: Scope | None) -> tuple[str, ...]:
        if scope is None:
            return ()
        return tuple(
            (scope.include_hosts or [])
            + (scope.include_cidrs or [])
            + (scope.include_domains or [])
        )

    @staticmethod
    def _raise_on_blocked(
        availability: object,
        action_id: str,
        engagement_id: str,
    ) -> None:
        from ambrosia.domain.action import ActionAvailability  # noqa: PLC0415
        from ambrosia.domain.errors import (
            MissingDependencyError,
            PolicyBlockedError,
        )

        if not isinstance(availability, ActionAvailability):
            return
        status = availability.status
        details = {
            "action_id": action_id,
            "engagement_id": engagement_id,
            "status": status,
            "reasons": list(availability.reasons),
        }
        if status == "blocked":
            # Distinguish scope violations from other policy blocks.
            if any(reason.startswith("blocked by scope") for reason in availability.reasons):
                raise ScopeViolationError(  # noqa: TRY003 - operator-facing message
                    "target is outside the authorized engagement scope",
                    details=details,
                )
            raise PolicyBlockedError(  # noqa: TRY003 - operator-facing message
                "execution is blocked by policy",
                details=details,
            )
        if status == "missing_dependency":
            raise MissingDependencyError(  # noqa: TRY003 - operator-facing message
                "a required dependency is unavailable",
                details=details,
            )
        if status == "needs_approval":
            raise PolicyBlockedError(  # noqa: TRY003 - operator-facing message
                "approval is required before execution",
                details={**details, "required_approval": True},
            )


__all__ = ["PolicyGateway"]
