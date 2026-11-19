"""Unit tests for the scope application service."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from tests.conftest import FakeEngagementRepository, FakeScopeRepository

from ambrosia.application.scope_service import ScopeService
from ambrosia.domain.errors import NotFoundError, ValidationError
from ambrosia.domain.models import Engagement, Scope


def _make_service() -> ScopeService:
    return ScopeService(
        session_scope=nullcontext,
        scope_repo=FakeScopeRepository(),
        engagement_repo=FakeEngagementRepository(),
    )


def test_show_returns_scope() -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab"))
    scope_repo.create(Scope(id="scope-1", engagement_id="eng-1"))

    service = ScopeService(
        session_scope=nullcontext, scope_repo=scope_repo, engagement_repo=eng_repo
    )
    dto = service.show("eng-1")

    assert dto.engagement_id == "eng-1"
    assert dto.include_hosts == []


def test_show_unknown_engagement_raises() -> None:
    service = _make_service()
    with pytest.raises(NotFoundError):
        service.show("does-not-exist")


def test_show_no_scope_raises() -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(__import__("ambrosia.domain.models", fromlist=["Engagement"]).Engagement(id="eng-1", name="lab"))

    service = ScopeService(
        session_scope=nullcontext, scope_repo=scope_repo, engagement_repo=eng_repo
    )
    with pytest.raises(NotFoundError):
        service.show("eng-1")


def test_update_rejects_include_exclude_overlap() -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab"))
    scope_repo.create(Scope(id="scope-1", engagement_id="eng-1"))

    service = ScopeService(
        session_scope=nullcontext, scope_repo=scope_repo, engagement_repo=eng_repo
    )
    with pytest.raises(ValidationError):
        service.update(
            "eng-1", include_hosts=["10.0.0.1"], exclude_hosts=["10.0.0.1"]
        )


def test_update_adds_fields() -> None:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab"))
    scope_repo.create(Scope(id="scope-1", engagement_id="eng-1"))

    service = ScopeService(
        session_scope=nullcontext, scope_repo=scope_repo, engagement_repo=eng_repo
    )
    dto = service.update(
        "eng-1",
        include_hosts=["10.0.0.1"],
        include_cidrs=["10.0.0.0/24"],
        allowed_ports=[445, 3389],
        max_concurrency=4,
    )

    assert dto.include_hosts == ["10.0.0.1"]
    assert dto.include_cidrs == ["10.0.0.0/24"]
    assert dto.allowed_ports == [445, 3389]
    assert dto.max_concurrency == 4
