"""Unit tests for the target application service."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from tests.conftest import (
    FakeEngagementRepository,
    FakeTargetRepository,
)

from ambrosia.application.target_service import TargetService
from ambrosia.domain.errors import NotFoundError, ValidationError
from ambrosia.domain.models import Engagement


def _make_service() -> TargetService:
    return TargetService(
        session_scope=nullcontext,
        target_repo=FakeTargetRepository(),
        engagement_repo=FakeEngagementRepository(),
    )


def test_add_detects_kind_and_creates_target() -> None:
    eng_repo = FakeEngagementRepository()
    target_repo = FakeTargetRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab"))

    service = TargetService(
        session_scope=nullcontext, target_repo=target_repo, engagement_repo=eng_repo
    )
    dto = service.add("eng-1", "10.0.0.1")
    assert dto.kind == "ip"

    dto = service.add("eng-1", "example.com")
    assert dto.kind == "domain"

    dto = service.add("eng-1", "myhost", kind="host")
    assert dto.kind == "host"
    assert len(target_repo.list_for_engagement("eng-1")) == 3


def test_add_unknown_engagement_raises() -> None:
    service = _make_service()
    with pytest.raises(NotFoundError):
        service.add("does-not-exist", "10.0.0.1")


def test_add_invalid_address_raises() -> None:
    eng_repo = FakeEngagementRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab"))
    service = TargetService(
        session_scope=nullcontext,
        target_repo=FakeTargetRepository(),
        engagement_repo=eng_repo,
    )
    with pytest.raises(ValidationError):
        service.add("eng-1", "not a valid address")


def test_list_returns_targets() -> None:
    eng_repo = FakeEngagementRepository()
    target_repo = FakeTargetRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab"))
    service = TargetService(
        session_scope=nullcontext, target_repo=target_repo, engagement_repo=eng_repo
    )
    service.add("eng-1", "10.0.0.1")
    service.add("eng-1", "example.com")

    dtos = service.list("eng-1")
    assert len(dtos.targets) == 2
