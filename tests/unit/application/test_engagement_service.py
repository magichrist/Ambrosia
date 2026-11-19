"""Unit tests for the engagement application service."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from tests.conftest import FakeEngagementRepository, FakeScopeRepository

from ambrosia.application.engagement_service import EngagementService
from ambrosia.domain.errors import NotFoundError


def _make_service() -> EngagementService:
    return EngagementService(
        session_scope=nullcontext,
        engagement_repo=FakeEngagementRepository(),
        scope_repo=FakeScopeRepository(),
    )


def test_create_sets_status_and_creates_scope() -> None:
    service = _make_service()
    dto = service.create(name="lab", description="lab engagement")

    assert dto.id
    assert dto.name == "lab"
    assert dto.description == "lab engagement"
    assert dto.status == "active"
    assert dto.scope_id is not None


def test_create_uses_shared_repos() -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    service = EngagementService(
        session_scope=nullcontext, engagement_repo=eng_repo, scope_repo=scope_repo
    )
    dto = service.create(name="lab")
    assert len(eng_repo.list()) == 1
    assert eng_repo.get(dto.id) is not None
    assert scope_repo.get_for_engagement(dto.id) is not None
    assert eng_repo.get(dto.id).scope_id == dto.scope_id


def test_list_returns_created_engagements() -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    service = EngagementService(
        session_scope=nullcontext, engagement_repo=eng_repo, scope_repo=scope_repo
    )
    service.create(name="one")
    service.create(name="two")

    dtos = service.list()
    assert [d.name for d in dtos.engagements] == ["one", "two"]


def test_get_unknown_raises_not_found() -> None:
    service = _make_service()
    with pytest.raises(NotFoundError):
        service.get("does-not-exist")


def test_open_is_alias_of_get() -> None:
    service = _make_service()
    dto = service.create(name="lab")
    assert service.open(dto.id) == service.get(dto.id)


def test_create_rejects_empty_name() -> None:
    service = _make_service()
    with pytest.raises(ValueError):
        service.create(name="   ")
