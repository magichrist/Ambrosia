"""Unit tests for the action application service."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeScopeRepository,
)

from ambrosia.actions.builtins import register_builtins
from ambrosia.application.action_service import ActionService
from ambrosia.domain.action import (
    ActionDefinition,
    ExecutorReference,
    ToolDependency,
)
from ambrosia.domain.errors import NotFoundError
from ambrosia.domain.models import Engagement, Scope
from ambrosia.registry import Registry


def _make_registry() -> Registry:
    registry = Registry()
    register_builtins(registry)

    discovery = ActionDefinition(
        id="network.nmap.service_discovery",
        version="1.0.0",
        name="Nmap Service Discovery",
        description="Discover services on a target.",
        category="discovery",
        tags=["discovery"],
        platforms=[],
        scope_fields=["target"],
        dependencies=[ToolDependency(name="nmap")],
        effects=["network_observe"],
        risk="low",
        executor=ExecutorReference(kind="process", executable="nmap"),
    )
    registry.register_builtin(discovery)

    blocked = ActionDefinition(
        id="test.remote_change",
        version="1.0.0",
        name="Blocked Change",
        description="An action with a disallowed effect.",
        category="test",
        tags=[],
        platforms=[],
        effects=["remote_change"],
        risk="high",
        executor=ExecutorReference(kind="native"),
    )
    registry.register_builtin(blocked)

    missing_dep = ActionDefinition(
        id="test.missing_dep",
        version="1.0.0",
        name="Missing Dependency",
        description="Needs a tool that is not installed.",
        category="test",
        tags=[],
        platforms=[],
        dependencies=[ToolDependency(name="nonexistent-tool-12345")],
        effects=["network_observe"],
        executor=ExecutorReference(kind="process", executable="nonexistent-tool-12345"),
    )
    registry.register_builtin(missing_dep)
    return registry


def _make_service(registry: Registry) -> ActionService:
    return ActionService(
        session_scope=nullcontext,
        registry=registry,
        engagement_repo=FakeEngagementRepository(),
        scope_repo=FakeScopeRepository(),
        artifact_repo=FakeArtifactRepository(),
    )


def _in_scope_engagement() -> tuple[FakeEngagementRepository, FakeScopeRepository]:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab", scope_id="scope-1"))
    scope_repo.create(
        Scope(
            id="scope-1",
            engagement_id="eng-1",
            include_hosts=["10.0.0.1"],
            allowed_effects={"local_read", "network_observe"},
        )
    )
    return eng_repo, scope_repo


def __engagement(id_: str):  # noqa: D401 - test helper
    from ambrosia.domain.models import Engagement

    return Engagement(id=id_, name="lab")


def test_list_returns_registered_actions() -> None:
    service = _make_service(_make_registry())
    dtos = service.list()
    ids = [d.id for d in dtos.actions]
    assert "core.echo" in ids
    assert "network.nmap.service_discovery" in ids


def test_info_returns_details() -> None:
    service = _make_service(_make_registry())
    dto = service.info("core.echo")
    assert dto.id == "core.echo"
    assert dto.executor_kind == "native"
    assert "local_read" in dto.effects


def test_info_unknown_raises() -> None:
    service = _make_service(_make_registry())
    with pytest.raises(NotFoundError):
        service.info("does-not-exist")


def test_check_available_with_target_in_scope() -> None:
    eng_repo, scope_repo = _in_scope_engagement()
    service = ActionService(
        session_scope=nullcontext,
        registry=_make_registry(),
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
        artifact_repo=FakeArtifactRepository(),
    )
    result = service.check(
        "network.nmap.service_discovery",
        engagement_id="eng-1",
        target_address="10.0.0.1",
    )
    assert result.allowed is True
    assert result.status == "available"


def test_check_blocked_outside_scope() -> None:
    eng_repo, scope_repo = _in_scope_engagement()
    service = ActionService(
        session_scope=nullcontext,
        registry=_make_registry(),
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
        artifact_repo=FakeArtifactRepository(),
    )
    result = service.check(
        "network.nmap.service_discovery",
        engagement_id="eng-1",
        target_address="99.99.99.99",
    )
    assert result.allowed is False
    assert result.status == "blocked"
    assert any("scope" in reason.lower() for reason in result.reasons)


def test_check_policy_blocked_effect() -> None:
    eng_repo, scope_repo = _in_scope_engagement()
    service = ActionService(
        session_scope=nullcontext,
        registry=_make_registry(),
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
        artifact_repo=FakeArtifactRepository(),
    )
    result = service.check("test.remote_change", engagement_id="eng-1", target_address="10.0.0.1")
    assert result.allowed is False
    assert result.status == "blocked"


def test_check_missing_dependency() -> None:
    eng_repo, scope_repo = _in_scope_engagement()
    service = ActionService(
        session_scope=nullcontext,
        registry=_make_registry(),
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
        artifact_repo=FakeArtifactRepository(),
    )
    result = service.check("test.missing_dep", engagement_id="eng-1", target_address="10.0.0.1")
    assert result.allowed is False
    assert result.status == "missing_dependency"
