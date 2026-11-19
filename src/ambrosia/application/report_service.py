"""Application service for report/evidence export."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from ambrosia.application._base import _BaseService
from ambrosia.domain.errors import NotFoundError, ValidationError

if TYPE_CHECKING:
    from typing import Any

    from ambrosia.application.protocols import TargetRepository as TargetRepositoryProtocol
    from ambrosia.domain.protocols import (
        ArtifactRepository as ArtifactRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        EngagementRepository as EngagementRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        ExecutionRepository as ExecutionRepositoryProtocol,
    )
    from ambrosia.domain.protocols import (
        ScopeRepository as ScopeRepositoryProtocol,
    )


class ReportExportDTO(BaseModel):
    path: str
    format: str
    engagement_id: str
    targets: int
    artifacts: int
    executions: int
    exported_at: str


class ReportService(_BaseService):
    def export(
        self,
        engagement_id: str,
        *,
        format: str = "json",
        output_path: str | None = None,
    ) -> ReportExportDTO:
        """Export an engagement evidence bundle as a JSON file.

        Only safe display data is exported: no secret values or references
        beyond their opaque handles.
        """
        if format != "json":
            raise ValidationError(  # noqa: TRY003 - operator-facing message
                f"unsupported report format: {format!r} (use 'json')"
            )

        exported_at = datetime.now(UTC).replace(tzinfo=None).isoformat()

        with self._session() as session:
            engagement_repo = cast(
                "EngagementRepositoryProtocol",
                self._repo("engagement_repo", session),
            )
            scope_repo = cast(
                "ScopeRepositoryProtocol", self._repo("scope_repo", session)
            )
            target_repo = cast(
                "TargetRepositoryProtocol",
                self._repo("target_repo", session),
            )
            artifact_repo = cast(
                "ArtifactRepositoryProtocol",
                self._repo("artifact_repo", session),
            )
            execution_repo = cast(
                "ExecutionRepositoryProtocol",
                self._repo("execution_repo", session),
            )

            if engagement_repo.get(engagement_id) is None:
                raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                    f"engagement {engagement_id!r} not found"
                )
            scope = scope_repo.get_for_engagement(engagement_id)
            targets = target_repo.list_for_engagement(engagement_id)
            artifacts = artifact_repo.list_for_engagement(engagement_id)
            executions = execution_repo.list_for_engagement(engagement_id)

            engagement = engagement_repo.get(engagement_id)
            bundle = {
                "engagement": {
                    "id": engagement_id,
                    "name": engagement.name if engagement is not None else "",
                },
                "scope": self._scope_summary(scope),
                "targets": [self._target_summary(t) for t in targets],
                "artifacts": [self._artifact_summary(a) for a in artifacts],
                "executions": [self._execution_summary(e) for e in executions],
                "exported_at": exported_at,
            }

        if output_path is None:
            output_path = str(Path.cwd() / f"ambrosia-report-{engagement_id}.json")
        path = Path(output_path)
        path.write_text(self._json(bundle) + "\n", encoding="utf-8")

        return ReportExportDTO(
            path=str(path.resolve()),
            format=format,
            engagement_id=engagement_id,
            targets=len(targets),
            artifacts=len(artifacts),
            executions=len(executions),
            exported_at=exported_at,
        )

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _json(value: object) -> str:
        import json

        return json.dumps(value, indent=2, sort_keys=True, default=str)

    @staticmethod
    def _scope_summary(scope: Any) -> dict[str, object] | None:
        if scope is None:
            return None
        return {
            "include_hosts": sorted(getattr(scope, "include_hosts", [])),
            "include_cidrs": sorted(getattr(scope, "include_cidrs", [])),
            "include_domains": sorted(getattr(scope, "include_domains", [])),
            "exclude_hosts": sorted(getattr(scope, "exclude_hosts", [])),
            "exclude_cidrs": sorted(getattr(scope, "exclude_cidrs", [])),
            "allowed_effects": sorted(getattr(scope, "allowed_effects", [])),
        }

    @staticmethod
    def _target_summary(target: Any) -> dict[str, object]:
        return {
            "id": target.id,
            "address": target.address,
            "kind": getattr(target, "kind", getattr(target, "target_type", "host")),
            "is_active": bool(getattr(target, "is_active", True)),
        }

    @staticmethod
    def _artifact_summary(artifact: Any) -> dict[str, object]:
        return {
            "id": artifact.id,
            "type": artifact.type,
            "sensitivity": artifact.sensitivity,
            "target_ref": artifact.target_ref,
            "source_kind": artifact.source_kind,
            "created_at": artifact.created_at.isoformat(),
        }

    @staticmethod
    def _execution_summary(execution: Any) -> dict[str, object]:
        started_at = execution.started_at
        finished_at = execution.finished_at
        return {
            "id": execution.id,
            "status": execution.status,
            "action_id": execution.action_id,
            "preset_id": execution.preset_id,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
        }


__all__ = ["ReportExportDTO", "ReportService"]
