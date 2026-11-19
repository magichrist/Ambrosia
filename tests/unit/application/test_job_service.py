"""Unit tests for the job application service."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

import pytest
from tests.conftest import FakeExecutionRepository

from ambrosia.application.job_service import JobService
from ambrosia.domain.errors import NotFoundError
from ambrosia.domain.models import ExecutionRecord


def _make_service() -> JobService:
    return JobService(
        session_scope=nullcontext,
        execution_repo=FakeExecutionRepository(),
    )


def _execution(id_: str, status: str = "succeeded") -> ExecutionRecord:
    return ExecutionRecord(
        id=id_,
        engagement_id="eng-1",
        action_id="core.echo",
        status=status,
        started_at=datetime.now(UTC).replace(tzinfo=None),
    )


def test_list_returns_executions() -> None:
    exec_repo = FakeExecutionRepository()
    exec_repo.add(_execution("e-1"))
    exec_repo.add(_execution("e-2", status="failed"))

    service = JobService(
        session_scope=nullcontext, execution_repo=exec_repo
    )
    dtos = service.list("eng-1")
    assert len(dtos.jobs) == 2


def test_show_returns_events() -> None:
    exec_repo = FakeExecutionRepository()
    exec_repo.add(_execution("e-1"))
    exec_repo.add_event("e-1", "ProgressEvent", {"message": "hi"}, 1)

    service = JobService(
        session_scope=nullcontext, execution_repo=exec_repo
    )
    dto = service.show("e-1")
    assert dto.job.id == "e-1"
    assert len(dto.events) == 1
    assert dto.events[0].kind == "ProgressEvent"


def test_show_unknown_raises() -> None:
    service = _make_service()
    with pytest.raises(NotFoundError):
        service.show("does-not-exist")


def test_cancel_marks_execution() -> None:
    exec_repo = FakeExecutionRepository()
    exec_repo.add(_execution("e-1", status="running"))

    service = JobService(
        session_scope=nullcontext, execution_repo=exec_repo
    )
    dto = service.cancel("e-1")
    assert dto.status == "cancelled"
    assert dto.finished_at is not None
