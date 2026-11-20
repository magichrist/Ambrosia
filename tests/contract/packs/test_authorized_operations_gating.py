# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Contract: the high-impact pack is opt-in and multiply gated."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeScopeRepository,
)

from ambrosia.application.policy_gateway import PolicyGateway
from ambrosia.domain.errors import PolicyBlockedError
from ambrosia.domain.models import Engagement, Scope
from ambrosia.executors.fake import FakeExecutor
from ambrosia.packs.authorized_operations import register_authorized_operations
from ambrosia.registry.loader import build_registry

ACTION = "windows.credentials.secretsdump"
TOOLS = frozenset({"secretsdump.py"})


def _gateway(registry, scope: Scope) -> PolicyGateway:
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab", scope_id="scope-1"))
    scope_repo.create(scope)
    return PolicyGateway(
        session_scope=nullcontext,
        registry=registry,
        engagement_repository=eng_repo,
        scope_repository=scope_repo,
        artifact_repository=FakeArtifactRepository(),
    )


def _default_scope() -> Scope:
    return Scope(id="scope-1", engagement_id="eng-1", include_hosts=["10.0.0.10"])


def test_default_registry_does_not_expose_high_impact_actions() -> None:
    registry = build_registry()
    assert not registry.has(ACTION)
    assert not any(definition.id.startswith("windows.lateral.") for definition in registry.list())


def test_authorization_gate_blocks_before_effect_check() -> None:
    registry = build_registry()
    register_authorized_operations(registry, executor=FakeExecutor())
    gateway = _gateway(registry, _default_scope())

    with pytest.raises(PolicyBlockedError, match="authorization reference"):
        gateway.check_action(action_id=ACTION, engagement_id="eng-1")


def test_default_scope_still_blocks_effect_with_authorization() -> None:
    registry = build_registry()
    register_authorized_operations(registry, executor=FakeExecutor())
    gateway = _gateway(registry, _default_scope())

    # With an authorization reference the effect allowlist is still enforced.
    with pytest.raises(PolicyBlockedError):
        gateway.check_action(
            action_id=ACTION,
            engagement_id="eng-1",
            available_tools=TOOLS,
            authorization_reference="ROE-1",
        )


def test_wide_scope_allows_effects_with_authorization() -> None:
    registry = build_registry()
    register_authorized_operations(registry, executor=FakeExecutor())
    scope = _default_scope()
    scope.allowed_effects = {  # type: ignore[misc]
        "local_read",
        "network_observe",
        "credential_access",
    }
    gateway = _gateway(registry, scope)

    result = gateway.check_action(
        action_id=ACTION,
        engagement_id="eng-1",
        available_tools=TOOLS,
        authorization_reference="ROE-1",
    )
    assert getattr(result, "action_id", None) == ACTION
