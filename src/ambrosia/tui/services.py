"""TUI service adapter.

Wraps :class:`ambrosia.application.ApplicationServices` (read operations) and
the optional :class:`ambrosia.engine.JobEngine` (execution) behind a small
async interface used by the Textual interface.

This adapter contains no business logic: scope checks, policy decisions, and
execution transitions all live in the service / engine layer. The TUI only
orchestrates presentation and streams results back to the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ambrosia.application import ApplicationServices
    from ambrosia.application.action_service import ActionCheckDTO, ActionDTO, ActionListDTO
    from ambrosia.application.engagement_service import EngagementDTO, EngagementListDTO
    from ambrosia.application.job_service import JobDTO, JobListDTO, JobShowDTO
    from ambrosia.application.preset_service import (
        PresetListDTO,
        PresetPlanDTO,
        PresetValidateDTO,
    )
    from ambrosia.application.report_service import ReportExportDTO
    from ambrosia.application.scope_service import ScopeDTO
    from ambrosia.application.target_service import TargetDTO, TargetListDTO
    from ambrosia.domain.action import ActionDefinition
    from ambrosia.domain.models import Artifact, Scope
    from ambrosia.domain.protocols import ArtifactRepository, ExecutionRepository
    from ambrosia.engine.engine import JobEngine

from ambrosia.domain.errors import AmbrosiaError


class ExecutionStarted(Message):
    """Marker: an execution was created."""

    def __init__(self, execution_id: str) -> None:
        super().__init__()
        self.execution_id = execution_id


class ExecutionEvent(Message):
    """A streamed execution event (progress/log/output/completed/failed)."""

    def __init__(
        self,
        execution_id: str,
        kind: str,
        payload: dict[str, object],
    ) -> None:
        super().__init__()
        self.execution_id = execution_id
        self.kind = kind
        self.payload = dict(payload)


class ExecutionFinished(Message):
    """Marker: an execution reached a terminal state."""

    def __init__(self, execution_id: str, status: str) -> None:
        super().__init__()
        self.execution_id = execution_id
        self.status = status


class ApprovalRequired(Message):
    """Marker: execution is awaiting operator approval."""

    def __init__(self, execution_id: str, approval_id: str) -> None:
        super().__init__()
        self.execution_id = execution_id
        self.approval_id = approval_id


class TUIServiceAdapter:
    """Adapts application services + the job engine for the TUI.

    Parameters
    ----------
    services:
        The application service container (read operations).
    engine:
        Optional job engine used to create, validate, and run executions. When
        ``None``, execution requests degrade to a "not available" result rather
        than failing noisily.
    execution_repo:
        Execution repository shared with the engine so execution history stays
        consistent with :class:`~ambrosia.application.job_service.JobService`.
    artifact_repo:
        Artifact repository used to list artifacts / findings.
    finding_repo:
        Optional finding repository. When absent, findings are read from the
        artifact repository filtered by type.
    """

    def __init__(
        self,
        *,
        services: ApplicationServices,
        engine: JobEngine | None = None,
        execution_repo: ExecutionRepository | None = None,
        artifact_repo: ArtifactRepository | None = None,
        finding_repo: object = None,
    ) -> None:
        self._services = services
        self._engine = engine
        self._execution_repo = execution_repo
        self._artifact_repo = artifact_repo
        self._finding_repo = finding_repo

    # ------------------------------------------------------------------ read

    def list_engagements(self) -> EngagementListDTO:
        return self._services.engagement.list()

    def create_engagement(self, name: str, description: str | None = None) -> EngagementDTO:
        return self._services.engagement.create(name=name, description=description)

    def get_engagement(self, engagement_id: str) -> EngagementDTO:
        return self._services.engagement.get(engagement_id)

    def show_scope(self, engagement_id: str) -> ScopeDTO:
        return self._services.scope.show(engagement_id)

    def update_scope(
        self,
        engagement_id: str,
        *,
        include_hosts: list[str] | None = None,
        include_cidrs: list[str] | None = None,
        include_domains: list[str] | None = None,
        exclude_hosts: list[str] | None = None,
        exclude_cidrs: list[str] | None = None,
        allowed_ports: list[int] | None = None,
        max_concurrency: int | None = None,
        max_requests_per_second: float | None = None,
        allowed_effects: list[str] | None = None,
        require_approval_for: list[str] | None = None,
        expires_at: str | None = None,
    ) -> ScopeDTO:
        return self._services.scope.update(
            engagement_id,
            include_hosts=include_hosts,
            include_cidrs=include_cidrs,
            include_domains=include_domains,
            exclude_hosts=exclude_hosts,
            exclude_cidrs=exclude_cidrs,
            allowed_ports=allowed_ports,
            max_concurrency=max_concurrency,
            max_requests_per_second=max_requests_per_second,
            allowed_effects=allowed_effects,
            require_approval_for=require_approval_for,
            expires_at=expires_at,
        )

    def list_targets(self, engagement_id: str) -> TargetListDTO:
        return self._services.target.list(engagement_id)

    def add_target(
        self,
        engagement_id: str,
        address: str,
        *,
        kind: str = "auto",
        hostname: str | None = None,
        notes: str | None = None,
    ) -> TargetDTO:
        return self._services.target.add(
            engagement_id, address, kind=kind, hostname=hostname, notes=notes
        )

    def list_actions(
        self,
        *,
        category: str | None = None,
        tag: str | None = None,
        platform: str | None = None,
    ) -> ActionListDTO:
        return self._services.action.list(category=category, tag=tag, platform=platform)

    def get_action(self, action_id: str) -> ActionDTO:
        return self._services.action.info(action_id)

    def check_action(
        self,
        action_id: str,
        *,
        engagement_id: str,
        target_address: str | None = None,
    ) -> ActionCheckDTO:
        return self._services.action.check(
            action_id, engagement_id=engagement_id, target_address=target_address
        )

    def list_presets(self) -> PresetListDTO:
        return self._services.preset.list()

    def validate_preset(self, path: str) -> PresetValidateDTO:
        return self._services.preset.validate(path)

    def plan_preset(self, preset_id: str) -> PresetPlanDTO:
        return self._services.preset.plan(preset_id)

    def list_artifacts(self, engagement_id: str) -> list[Artifact]:
        if self._artifact_repo is None:
            return []
        return self._artifact_repo.list_for_engagement(engagement_id)

    def list_findings(self, engagement_id: str) -> list[Artifact]:
        if self._finding_repo is not None:
            # Prefer the dedicated finding repository when available.
            items = getattr(self._finding_repo, "list_for_engagement", None)
            if items is not None:
                return list(items(engagement_id))
            return []
        artifacts = self.list_artifacts(engagement_id)
        return [a for a in artifacts if a.type == "finding" or a.type.startswith("finding.")]

    def job_list(self, engagement_id: str) -> JobListDTO:
        return self._services.job.list(engagement_id)

    def job_show(self, execution_id: str) -> JobShowDTO:
        return self._services.job.show(execution_id)

    def job_cancel(self, execution_id: str) -> JobDTO:
        return self._services.job.cancel(execution_id)

    def export_report(
        self,
        engagement_id: str,
        *,
        output_path: str | None = None,
    ) -> ReportExportDTO:
        return self._services.report.export(engagement_id, output_path=output_path)

    # ------------------------------------------------------------------ scope helper

    def scope_domain(self, engagement_id: str) -> Scope:
        """Build a domain :class:`~ambrosia.domain.models.Scope` from the DTO.

        Pure data mapping; the engine owns the actual scope check.
        """
        from ambrosia.domain.models import Scope

        dto = self.show_scope(engagement_id)
        expires_at = None
        if dto.expires_at is not None:
            from datetime import datetime

            expires_at = datetime.fromisoformat(dto.expires_at)
        return Scope(
            engagement_id=engagement_id,
            include_hosts=list(dto.include_hosts),
            include_cidrs=list(dto.include_cidrs),
            include_domains=list(dto.include_domains),
            exclude_hosts=list(dto.exclude_hosts),
            exclude_cidrs=list(dto.exclude_cidrs),
            allowed_ports=list(dto.allowed_ports) if dto.allowed_ports is not None else None,
            expires_at=expires_at,
            max_concurrency=dto.max_concurrency,
            max_requests_per_second=dto.max_requests_per_second,
            allowed_effects=set(dto.allowed_effects),
            require_approval_for=set(dto.require_approval_for),
        )

    # ------------------------------------------------------------------ execution

    @property
    def engine(self) -> JobEngine | None:
        return self._engine

    def registry(self) -> object:
        return self._services.registry

    def action_definition(self, action_id: str) -> ActionDefinition | None:
        return self._services.registry.get(action_id)

    async def run_action(
        self,
        action_id: str,
        *,
        engagement_id: str,
        target_address: str | None = None,
        inputs: dict[str, object] | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Create, validate, and run an execution, streaming events.

        Yields dicts with keys:
          * ``{"kind": "started", "execution_id": ...}``
          * ``{"kind": "event", "execution_id": ..., "event_kind": ..., "payload": ...}``
          * ``{"kind": "approval_required", "execution_id": ..., "approval_id": ...}``
          * ``{"kind": "finished", "execution_id": ..., "status": ...}``

        Raises :class:`~ambrosia.domain.errors.AmbrosiaError` on validation /
        policy / scope failure so the caller can present the reason.
        """
        if self._engine is None:
            from ambrosia.domain.errors import MissingDependencyError

            raise MissingDependencyError(
                "execution engine is not integrated; use 'preset plan' to inspect actions",
                details={"action_id": action_id},
            )

        definition = self._services.registry.get(action_id)
        if definition is None:
            from ambrosia.domain.errors import NotFoundError

            raise NotFoundError(f"action {action_id!r} is not registered")

        inputs = dict(inputs or {})

        execution_id = await self._engine.create_job(
            engagement_id=engagement_id,
            action_id=action_id,
            inputs=inputs,
            target_refs=[target_address] if target_address else [],
        )
        yield {"kind": "started", "execution_id": execution_id}

        scope = self.scope_domain(engagement_id)
        await self._engine.validate_job(execution_id, scope=scope, address=target_address)

        approval_id = await self._engine.request_approval(execution_id)
        if approval_id is not None:
            yield {
                "kind": "approval_required",
                "execution_id": execution_id,
                "approval_id": approval_id,
            }
            return

        timeout = definition.timeout_seconds
        async for event in self._engine.run_job(execution_id, timeout_seconds=timeout):
            yield {
                "kind": "event",
                "execution_id": execution_id,
                "event_kind": event.kind,
                "payload": dict(event.payload),
            }

        job = self._services.job.show(execution_id).job
        yield {"kind": "finished", "execution_id": execution_id, "status": job.status}

    async def dry_run_action(
        self,
        action_id: str,
        *,
        engagement_id: str,
        target_address: str | None = None,
        inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Produce a sanitized execution plan without launching any process."""
        if self._engine is None:
            from ambrosia.domain.errors import MissingDependencyError

            raise MissingDependencyError(
                "execution engine is not integrated",
                details={"action_id": action_id},
            )
        definition = self._services.registry.get(action_id)
        if definition is None:
            from ambrosia.domain.errors import NotFoundError

            raise NotFoundError(f"action {action_id!r} is not registered")

        execution_id = await self._engine.create_job(
            engagement_id=engagement_id,
            action_id=action_id,
            inputs=dict(inputs or {}),
            target_refs=[target_address] if target_address else [],
        )
        scope = self.scope_domain(engagement_id)
        return await self._engine.dry_run(execution_id, scope=scope, address=target_address)

    async def grant_approval(
        self,
        execution_id: str,
        approval_id: str,
        *,
        decided_by: str = "operator",
    ) -> None:
        if self._engine is None:
            from ambrosia.domain.errors import MissingDependencyError

            raise MissingDependencyError(
                "execution engine is not integrated",
                details={"execution_id": execution_id},
            )
        await self._engine.grant_approval(
            execution_id, approval_id=approval_id, decided_by=decided_by
        )

    async def deny_approval(
        self,
        execution_id: str,
        approval_id: str,
        *,
        decided_by: str = "operator",
        reason: str | None = None,
    ) -> None:
        if self._engine is None:
            from ambrosia.domain.errors import MissingDependencyError

            raise MissingDependencyError(
                "execution engine is not integrated",
                details={"execution_id": execution_id},
            )
        await self._engine.deny_approval(
            execution_id,
            approval_id=approval_id,
            decided_by=decided_by,
            reason=reason,
        )

    async def cancel_job(self, execution_id: str) -> None:
        """Cancel a running execution (engine task + persisted status)."""
        if self._engine is not None:
            try:
                await self._engine.cancel_job(execution_id)
            except AmbrosiaError:
                # The engine may not be tracking the task; persist the status
                # change below regardless.
                pass
        self._services.job.cancel(execution_id)


__all__ = [
    "TUIServiceAdapter",
    "ExecutionStarted",
    "ExecutionEvent",
    "ExecutionFinished",
    "ApprovalRequired",
]
