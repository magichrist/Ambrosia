"""Unit tests for the report application service."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import pytest
from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeExecutionRepository,
    FakeScopeRepository,
    FakeTargetRepository,
)

from ambrosia.application.report_service import ReportService
from ambrosia.domain.errors import NotFoundError, ValidationError


def _make_service() -> ReportService:
    return ReportService(
        session_scope=nullcontext,
        engagement_repo=FakeEngagementRepository(),
        scope_repo=FakeScopeRepository(),
        target_repo=FakeTargetRepository(),
        artifact_repo=FakeArtifactRepository(),
        execution_repo=FakeExecutionRepository(),
    )


def test_export_unsupported_format_raises() -> None:
    service = _make_service()
    with pytest.raises(ValidationError):
        service.export("eng-1", format="xml")


def test_export_unknown_engagement_raises() -> None:
    service = _make_service()
    with pytest.raises(NotFoundError):
        service.export("does-not-exist")


def test_export_writes_json(tmp_path) -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    target_repo = FakeTargetRepository()
    artifact_repo = FakeArtifactRepository()
    execution_repo = FakeExecutionRepository()
    eng_repo.create(__engagement("eng-1"))
    target_repo.create(
        engagement_id="eng-1", address="10.0.0.1", target_type="ip"
    )
    service = ReportService(
        session_scope=nullcontext,
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
        target_repo=target_repo,
        artifact_repo=artifact_repo,
        execution_repo=execution_repo,
    )
    out = tmp_path / "report.json"
    dto = service.export("eng-1", output_path=str(out))

    assert dto.format == "json"
    assert dto.targets == 1
    assert Path(out).is_file()
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["engagement"]["id"] == "eng-1"
    assert "scope" in data
    assert "targets" in data


def __engagement(id_: str):  # noqa: D401 - test helper
    from ambrosia.domain.models import Engagement

    return Engagement(id=id_, name="lab")
