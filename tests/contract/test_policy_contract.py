# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Contract tests for the policy engine.

Covers scope include/exclude behavior, DNS resolution boundary, expiry,
target-outside-scope blocking on every path, policy effects, and approval
transitions.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.errors import PolicyBlockedError, ScopeViolationError
from ambrosia.domain.models import Scope
from ambrosia.policy import (
    EffectClassifier,
    PolicyDecision,
    PolicyEngine,
    ScopeChecker,
    require_policy_allowed,
)


def _scope(**overrides) -> Scope:
    data = {
        "id": "scope-1",
        "engagement_id": "eng-1",
        "include_hosts": ["10.0.0.1"],
        "include_cidrs": ["10.0.0.0/24"],
        "include_domains": ["example.com"],
        "exclude_hosts": ["10.0.0.99"],
        "exclude_cidrs": ["10.0.0.128/25"],
        "allowed_ports": [80, 443],
        "max_concurrency": 2,
        "allowed_effects": {"local_read", "network_observe"},
        "require_approval_for": {"local_write", "remote_change"},
    }
    data.update(overrides)
    return Scope(**data)


def _action(**overrides) -> ActionDefinition:
    data = {
        "id": "test.action",
        "version": "1.0.0",
        "name": "Test",
        "description": "A test action.",
        "category": "test",
        "executor": ExecutorReference(kind="process", executable="fake-tool"),
        "effects": ["local_read"],
        "scope_fields": ["target"],
        "approval_required": False,
    }
    data.update(overrides)
    return ActionDefinition(**data)


# ---------------------------------------------------------------------------
# Scope include/exclude


def test_include_exact_ip() -> None:
    checker = ScopeChecker()
    assert checker.is_address_in_scope("10.0.0.1", _scope()).in_scope is True


def test_include_cidr() -> None:
    checker = ScopeChecker()
    assert checker.is_address_in_scope("10.0.0.42", _scope()).in_scope is True


def test_include_domain_suffix() -> None:
    checker = ScopeChecker()
    assert checker.is_address_in_scope("api.example.com", _scope()).in_scope is True


def test_exclude_host_wins() -> None:
    checker = ScopeChecker()
    assert checker.is_address_in_scope("10.0.0.99", _scope()).in_scope is False


def test_exclude_cidr_wins() -> None:
    checker = ScopeChecker()
    assert checker.is_address_in_scope("10.0.0.200", _scope()).in_scope is False


def test_empty_scope_allows_nothing() -> None:
    checker = ScopeChecker()
    result = checker.is_address_in_scope(
        "10.0.0.1",
        _scope(include_hosts=[], include_cidrs=[], include_domains=[]),
    )
    assert result.in_scope is False


# ---------------------------------------------------------------------------
# Expiry


def test_scope_expiry_blocks() -> None:
    checker = ScopeChecker()
    past = datetime.utcnow() - timedelta(days=1)
    with pytest.raises(ScopeViolationError):
        checker.check_target("10.0.0.1", scope=_scope(expires_at=past))


def test_scope_future_not_expired() -> None:
    checker = ScopeChecker()
    future = datetime.utcnow() + timedelta(days=7)
    assert checker.is_expired(_scope(expires_at=future)) is False


# ---------------------------------------------------------------------------
# Target outside scope blocked on every path


def test_outside_scope_blocked_by_check_target() -> None:
    checker = ScopeChecker()
    with pytest.raises(ScopeViolationError):
        checker.check_target("99.99.99.99", scope=_scope())


def test_outside_scope_blocked_by_policy_engine() -> None:
    engine = PolicyEngine()
    outcome, decision, record = engine.evaluate(
        action=_action(scope_fields=["target"]),
        scope=_scope(),
        address="99.99.99.99",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "blocked"
    assert record.blocked is True


def test_outside_scope_blocked_by_dry_run() -> None:
    # Dry run evaluates policy but launches no process; outside scope is blocked.
    engine = PolicyEngine()
    outcome, _decision, _record = engine.evaluate(
        action=_action(scope_fields=["target"]),
        scope=_scope(),
        address="99.99.99.99",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "blocked"


# ---------------------------------------------------------------------------
# Policy effects and approval transitions


def test_effect_classification_allowed() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["local_read", "network_observe"],
        allowed_effects=frozenset({"local_read", "network_observe"}),
        require_approval_for=frozenset(),
    )
    assert result.is_fully_allowed is True


def test_effect_classification_blocked() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["remote_change"],
        allowed_effects=frozenset({"local_read"}),
        require_approval_for=frozenset(),
    )
    assert result.is_fully_allowed is False
    assert "remote_change" in result.blocked


def test_effect_classification_requires_approval() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["local_write"],
        allowed_effects=frozenset({"local_read", "local_write"}),
        require_approval_for=frozenset({"local_write"}),
    )
    assert result.is_fully_allowed is False
    assert "local_write" in result.requires_approval


def test_unknown_effect_is_blocked() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["unknown_future_effect"],
        allowed_effects=frozenset({"local_read"}),
        require_approval_for=frozenset(),
    )
    assert result.has_unknown is True
    assert "unknown_future_effect" in result.blocked


def test_policy_engine_requires_approval_outcome() -> None:
    engine = PolicyEngine()
    outcome, decision, record = engine.evaluate(
        action=_action(effects=["local_write"], approval_required=True),
        scope=_scope(allowed_effects={"local_read", "local_write", "network_observe"}),
        address="10.0.0.1",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "requires_approval"
    assert record.requires_approval is True


def test_require_policy_allowed_raises_on_blocked() -> None:
    decision = PolicyDecision(
        execution_id="exec-1",
        action_id="test.action",
        engagement_id="eng-1",
        outcome="blocked",
        reason="blocked by policy",
    )
    with pytest.raises(PolicyBlockedError):
        require_policy_allowed("blocked", decision)


def test_approval_state_transitions() -> None:
    from ambrosia.policy import ApprovalService

    service = ApprovalService()
    record = service.create(
        execution_id="exec-1",
        engagement_id="eng-1",
        effect="local_write",
        reason="sensitive effect",
    )
    assert record.state == "pending"

    granted = service.grant(record.id, decided_by="operator")
    assert granted.state == "granted"

    denied = service.create(
        execution_id="exec-2",
        engagement_id="eng-1",
        effect="remote_change",
    )
    denied = service.deny(denied.id, decided_by="operator", reason="no")
    assert denied.state == "denied"
