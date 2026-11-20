"""The application service container and its production factory.

``ApplicationServices`` aggregates all use-case services. Tests build it with
fake repositories (and no storage); production builds it through
:func:`load_services` from a :class:`ambrosia.storage.Storage` and a registry.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

from ambrosia.application.action_service import ActionService
from ambrosia.application.engagement_service import EngagementService
from ambrosia.application.job_service import JobService
from ambrosia.application.policy_gateway import PolicyGateway
from ambrosia.application.preset_service import PresetService
from ambrosia.application.report_service import ReportService
from ambrosia.application.scope_service import ScopeService
from ambrosia.application.target_service import TargetService
from ambrosia.application.workspace import workspace_dir

if TYPE_CHECKING:
    from collections.abc import Callable

    from ambrosia.application.protocols import PresetEngine
    from ambrosia.domain.protocols import (
        EngagementRepository as EngagementRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        ScopeRepository as ScopeRepositoryProtocol,
    )
    from ambrosia.registry import Registry


class ApplicationServices:
    """All application services, wired to a shared set of repositories."""

    def __init__(
        self,
        *,
        session_scope: Callable[[], AbstractContextManager[object | None]] = nullcontext,
        registry: Registry,
        presets_dirs: tuple[str, ...] = (),
        engine: PresetEngine | None = None,
        user_presets_dir: Path | None = None,
        engagement_repo: EngagementRepositoryProtocol | None = None,
        scope_repo: ScopeRepositoryProtocol | None = None,
        artifact_repo: object = None,
        execution_repo: object = None,
        target_repo: object = None,
        finding_repo: object = None,
        approval_repo: object = None,
        evidence_repo: object = None,
    ) -> None:
        self.registry = registry
        self.presets_dirs = [Path(directory) for directory in presets_dirs]
        self.engine = engine
        session = session_scope

        self.engagement = EngagementService(
            session_scope=session,
            engagement_repo=engagement_repo,
            scope_repo=scope_repo,
        )
        self.scope = ScopeService(
            session_scope=session,
            scope_repo=scope_repo,
            engagement_repo=engagement_repo,
        )
        self.target = TargetService(
            session_scope=session,
            target_repo=target_repo,
            engagement_repo=engagement_repo,
        )
        self.action = ActionService(
            session_scope=session,
            registry=registry,
            engagement_repo=engagement_repo,
            scope_repo=scope_repo,
            artifact_repo=artifact_repo,
        )
        self.preset = PresetService(
            session_scope=session,
            registry=registry,
            presets_dirs=self.presets_dirs,
            engine=engine,
            user_presets_dir=user_presets_dir or (workspace_dir() / "presets"),
            scope_repo=scope_repo,
            engagement_repo=engagement_repo,
            artifact_repo=artifact_repo,
        )
        self.job = JobService(
            session_scope=session,
            execution_repo=execution_repo,
        )
        self.report = ReportService(
            session_scope=session,
            engagement_repo=engagement_repo,
            scope_repo=scope_repo,
            target_repo=target_repo,
            artifact_repo=artifact_repo,
            execution_repo=execution_repo,
        )
        self.policy = PolicyGateway(
            session_scope=session,
            registry=registry,
            engagement_repository=engagement_repo,
            scope_repository=scope_repo,
            artifact_repository=artifact_repo,
        )


def load_services(
    *,
    storage: object,
    registry: Registry,
    presets_dirs: tuple[str, ...] = (),
    engine: PresetEngine | None = None,
    user_presets_dir: Path | None = None,
) -> ApplicationServices:
    """Build production services backed by SQLAlchemy repositories.

    Each service method opens its own transactional session from ``storage``,
    so a CLI invocation (one process, one command) commits its work on exit.
    """
    from ambrosia.storage import Storage

    if not isinstance(storage, Storage):  # pragma: no cover - defensive
        message = "load_services requires an ambrosia.storage.Storage instance"
        raise TypeError(message)

    # Production services must expose the built-in domain packs even when the
    # caller supplied a bare registry. ``build_registry`` (CLI/TUI startup) has
    # already registered them, so this is guarded and idempotent. Registration
    # is metadata-only and never executes a tool.
    if not registry.has("network.nmap.service_discovery"):
        from ambrosia.packs.windows_assessment import register_pack

        register_pack(registry)

    return ApplicationServices(
        session_scope=storage.session,
        registry=registry,
        presets_dirs=presets_dirs,
        engine=engine,
        user_presets_dir=user_presets_dir,
    )


__all__ = ["ApplicationServices", "load_services"]
