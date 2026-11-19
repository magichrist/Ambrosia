"""Application service for executions (jobs)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from pydantic import BaseModel

from ambrosia.domain.errors import NotFoundError
from ambrosia.domain.models import ExecutionRecord
from ambrosia.domain.protocols import (
    ExecutionRepository as ExecutionRepositoryProtocol,
)
from ambrosia.application._base import _BaseService


class JobDTO(BaseModel):
    id: str
    engagement_id: str
    action_id: str | None = None
    preset_id: str | None = None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    target_refs: list[str]
    input_summary: dict[str, object]
    output_artifact_ids: list[str]
    error_code: str | None = None
    error_message: str | None = None
    initiated_by: str


class JobListDTO(BaseModel):
    jobs: list[JobDTO]


class JobEventDTO(BaseModel):
    id: int | None = None
    kind: str
    payload: dict[str, object]
    timestamp: str | None = None
    sequence: int | None = None


class JobShowDTO(BaseModel):
    job: JobDTO
    events: list[JobEventDTO]


class JobService(_BaseService):
    def list(self, engagement_id: str) -> JobListDTO:
        with self._session() as session:
            execution_repo = cast(
                ExecutionRepositoryProtocol, self._repo("execution_repo", session)
            )
            executions = execution_repo.list_for_engagement(engagement_id)
            return JobListDTO(jobs=[self._dto(e) for e in executions])

    def show(self, execution_id: str) -> JobShowDTO:
        with self._session() as session:
            execution_repo = cast(
                ExecutionRepositoryProtocol, self._repo("execution_repo", session)
            )
            execution = execution_repo.get(execution_id)
            if execution is None:
                raise NotFoundError(f"execution {execution_id!r} not found")
            events: list[JobEventDTO] = []
            list_events = getattr(execution_repo, "list_events", None)
            if list_events is not None:
                for event in list_events(execution_id):
                    timestamp = event.get("timestamp")
                    events.append(
                        JobEventDTO(
                            id=event.get("id"),
                            kind=event.get("kind", ""),
                            payload=event.get("payload", {}),
                            timestamp=(
                                timestamp.isoformat()
                                if isinstance(timestamp, datetime)
                                else str(timestamp or "")
                            ),
                            sequence=event.get("sequence"),
                        )
                    )
            return JobShowDTO(job=self._dto(execution), events=events)

    def cancel(self, execution_id: str) -> JobDTO:
        with self._session() as session:
            execution_repo = cast(
                ExecutionRepositoryProtocol, self._repo("execution_repo", session)
            )
            execution = execution_repo.get(execution_id)
            if execution is None:
                raise NotFoundError(f"execution {execution_id!r} not found")
            execution.status = "cancelled"
            execution.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            execution_repo.update(execution)
            return self._dto(execution)

    @staticmethod
    def _dto(execution: ExecutionRecord) -> JobDTO:
        return JobDTO(
            id=execution.id,
            engagement_id=execution.engagement_id,
            action_id=execution.action_id,
            preset_id=execution.preset_id,
            status=execution.status,
            started_at=execution.started_at.isoformat() if execution.started_at else None,
            finished_at=execution.finished_at.isoformat() if execution.finished_at else None,
            target_refs=list(execution.target_refs),
            input_summary=dict(execution.input_summary),
            output_artifact_ids=list(execution.output_artifact_ids),
            error_code=execution.error_code,
            error_message=execution.error_message,
            initiated_by=execution.initiated_by,
        )


__all__ = ["JobDTO", "JobListDTO", "JobShowDTO", "JobEventDTO", "JobService"]
