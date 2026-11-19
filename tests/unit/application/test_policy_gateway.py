"""Unit tests for the policy gateway application service."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeScopeRepository,
)

from ambrosia.actions.builtins import register_builtins
from ambrosia.application.policy_gateway import PolicyGateway
from ambrosia.domain.action import ActionDefinition, ExecutorReference, ToolDependency
from ambrosia.domain.errors import (
    MissingDependencyError,
    NotFoundError,
    PolicyBlockedError,
    ScopeViolationError,
)
from ambrosia.domain.models import Engagement, Scope
from ambrosia.registry import Registry


def _make_gateway(
    registry: Registry,
    engagement_repo: FakeEngagementRepository | None = None,
    scope_repo: FakeScopeRepository | None = None,
) -> PolicyGateway:
    return PolicyGateway(
        session_scope=nullcontext,
        registry=registry,
        engagement_repository=engagement_repo or FakeEngagementRepository(),
        scope_repository=scope_repo or FakeScopeRepository(),
        artifact_repository=FakeArtifactRepository(),
    )


def _registry_with_actions() -> Registry:
    registry = Registry()
    register_builtins(registry)

    discovery = ActionDefinition(
        id="network.nmap.service_discovery",
        version="1.0.0",
        name="Discovery",
        description="discover",
        category="discovery",
        tags=[],
        platforms=[],
        scope_fields=["target"],
        effects=["network_observe"],
        risk="low",
        executor=ExecutorReference(kind="process", executable="nmap"),
    )
    registry.register_builtin(discovery)

    change = ActionDefinition(
        id="test.change",
        version="1.0.0",
        name="Change",
        description="change",
        category="test",
        tags=[],
        platforms=[],
        effects=["remote_change"],
        risk="high",
        executor=ExecutorReference(kind="native"),
    )
    registry.register_builtin(change)
    return registry


def _in_scope() -> tuple[FakeEngagementRepository, FakeScopeRepository]:
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


def test_check_action_unknown_raises_not_found() -> None:
    gateway = _make_gateway(_registry_with_actions())
    with pytest.raises(NotFoundError):
        gateway.check_action(
            action_id="does-not-exist", engagement_id="eng-1"
        )


def test_check_action_no_scope_raises_scope_violation() -> None:
    registry = _registry_with_actions()
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(__engagement("eng-1"))
    # No scope for the engagement.
    gateway = PolicyGateway(
        session_scope=nullcontext,
        registry=registry,
        engagement_repository=eng_repo,
        scope_repository=scope_repo,
        artifact_repository=FakeArtifactRepository(),
    )
    with pytest.raises(ScopeViolationError):
        gateway.check_action(
            action_id="network.nmap.service_discovery",
            engagement_id="eng-1",
            target_address="10.0.0.1",
        )


def test_check_action_outside_scope_raises_scope_violation() -> None:
    eng_repo, scope_repo = _in_scope()
    gateway = _make_gateway(_registry_with_actions(), eng_repo, scope_repo)
    with pytest.raises(ScopeViolationError):
        gateway.check_action(
            action_id="network.nmap.service_discovery",
            engagement_id="eng-1",
            target_address="99.99.99.99",
        )


def test_check_action_disallowed_effect_raises_policy_blocked() -> None:
    eng_repo, scope_repo = _in_scope()
    gateway = _make_gateway(_registry_with_actions(), eng_repo, scope_repo)
    with pytest.raises(PolicyBlockedError):
        gateway.check_action(
            action_id="test.change", engagement_id="eng-1", target_address="10.0.0.1"
        )


def test_check_action_allowed_returns_availability() -> None:
    eng_repo, scope_repo = _in_scope()
    gateway = _make_gateway(_registry_with_actions(), eng_repo, scope_repo)
    availability = gateway.check_action(
        action_id="network.nmap.service_discovery",
        engagement_id="eng-1",
        target_address="10.0.0.1",
    )
    assert availability.status == "available"
    assert availability.required_approval is False


def test_check_action_missing_dependency_raises() -> None:
    registry = Registry()
    register_builtins(registry)
    dep_action = ActionDefinition(
        id="test.dep",
        version="1.0.0",
        name="Dep",
        description="dep",
        category="test",
        tags=[],
        platforms=[],
        dependencies=[ToolDependency(name="nmap")],
        effects=["network_observe"],
        executor=ExecutorReference(kind="process", executable="nmap"),
    )
    registry.register_builtin(dep_action)
    eng_repo, scope_repo = _in_scope()
    gateway = PolicyGateway(
        session_scope=nullcontext,
        registry=registry,
        engagement_repository=eng_repo,
        scope_repository=scope_repo,
        artifact_repository=FakeArtifactRepository(),
    )
    # nmap is not on PATH as a dependency -> missing_dependency (tool dep check is
    # metadata-only via available_tools, which is empty here).
    with pytest.raises(MissingDependencyError):
        gateway.check_action(
            action_id="test.dep", engagement_id="eng-1", target_address="10.0.0.1",
            available_tools=frozenset(),
        )
