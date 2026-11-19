# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for effect classification and approval state transitions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.models import Scope
from ambrosia.domain.errors import ConflictError, NotFoundError, PolicyBlockedError
from ambrosia.policy import (
    ApprovalRecord,
    ApprovalService,
    ApprovalState,
    EffectClassifier,
    EffectClassification,
    PolicyDecision,
    PolicyDecisionRecord,
    PolicyEngine,
    require_policy_allowed,
)


def _scope(**overrides) -> Scope:
    data = dict(
        id="scope-1",
        engagement_id="eng-1",
        include_hosts=["10.0.0.1"],
        include_cidrs=[],
        include_domains=[],
        exclude_hosts=[],
        exclude_cidrs=[],
        allowed_ports=None,
        max_concurrency=2,
        allowed_effects={"local_read", "network_observe"},
        require_approval_for={"local_write", "remote_change", "authentication"},
    )
    data.update(overrides)
    return Scope(**data)


def _action(**overrides) -> ActionDefinition:
    data = dict(
        id="test.action",
        version="1.0.0",
        name="Test",
        description="A test action.",
        category="test",
        executor=ExecutorReference(kind="process", executable="fake-tool"),
        effects=["local_read"],
        scope_fields=["target"],
        approval_required=False,
    )
    data.update(overrides)
    return ActionDefinition(**data)


# ---------------------------------------------------------------------------
# Effect classification

def test_classify_all_allowed() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["local_read", "network_observe"],
        allowed_effects=frozenset({"local_read", "network_observe"}),
        require_approval_for=frozenset(),
    )
    assert result.is_fully_allowed is True
    assert result.allowed == ("local_read", "network_observe")
    assert result.blocked == ()
    assert result.requires_approval == ()


def test_classify_blocked_effect() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["remote_change"],
        allowed_effects=frozenset({"local_read"}),
        require_approval_for=frozenset(),
    )
    assert result.is_fully_allowed is False
    assert "remote_change" in result.blocked


def test_classify_requires_approval() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["local_write"],
        allowed_effects=frozenset({"local_read", "local_write"}),
        require_approval_for=frozenset({"local_write"}),
    )
    assert result.is_fully_allowed is False
    assert "local_write" in result.requires_approval


def test_classify_unknown_effect_blocked() -> None:
    classifier = EffectClassifier()
    result = classifier.classify(
        ["weird_effect"],
        allowed_effects=frozenset({"local_read"}),
        require_approval_for=frozenset(),
    )
    assert result.has_unknown is True
    assert "weird_effect" in result.blocked


# ---------------------------------------------------------------------------
# Policy decision records

def test_policy_decision_to_dict_is_secret_free() -> None:
    decision = PolicyDecision(
        execution_id="exec-1",
        action_id="test.action",
        engagement_id="eng-1",
        outcome="allowed",
        reason="all clear",
        scope_address="10.0.0.1",
        scope_in_scope=True,
    )
    data = decision.to_dict()
    assert data["execution_id"] == "exec-1"
    assert data["scope_address"] == "10.0.0.1"
    # No secret values anywhere.
    assert "[REDACTED]" not in str(data)


def test_policy_decision_record_immutable_append() -> None:
    record = PolicyDecisionRecord(execution_id="exec-1")
    d1 = PolicyDecision(
        execution_id="exec-1",
        action_id="a",
        engagement_id="e",
        outcome="allowed",
    )
    record2 = record.add(d1)
    assert record is not record2
    assert len(record.decisions) == 0
    assert len(record2.decisions) == 1
    assert record2.allowed is True


def test_policy_decision_record_blocked_and_approval() -> None:
    record = PolicyDecisionRecord(execution_id="exec-1")
    record = record.add(PolicyDecision(
        execution_id="exec-1", action_id="a", engagement_id="e",
        outcome="blocked", reason="out of scope",
    ))
    record = record.add(PolicyDecision(
        execution_id="exec-1", action_id="a", engagement_id="e",
        outcome="requires_approval", reason="needs approval",
    ))
    assert record.blocked is True
    assert record.requires_approval is True
    assert record.allowed is False


# ---------------------------------------------------------------------------
# PolicyEngine.evaluate

def test_engine_evaluate_allowed() -> None:
    engine = PolicyEngine()
    outcome, decision, record = engine.evaluate(
        action=_action(effects=["local_read"]),
        scope=_scope(),
        address="10.0.0.1",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "allowed"
    assert record.allowed is True


def test_engine_evaluate_blocked_by_scope() -> None:
    engine = PolicyEngine()
    outcome, decision, record = engine.evaluate(
        action=_action(effects=["local_read"], scope_fields=["target"]),
        scope=_scope(),
        address="99.99.99.99",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "blocked"
    assert record.blocked is True


def test_engine_evaluate_requires_approval() -> None:
    engine = PolicyEngine()
    outcome, decision, record = engine.evaluate(
        action=_action(effects=["local_write"], approval_required=True),
        scope=_scope(
            allowed_effects={"local_read", "local_write", "network_observe"}
        ),
        address="10.0.0.1",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "requires_approval"
    assert record.requires_approval is True


def test_require_policy_allowed_raises() -> None:
    decision = PolicyDecision(
        execution_id="exec-1",
        action_id="a",
        engagement_id="e",
        outcome="blocked",
        reason="blocked",
    )
    with pytest.raises(PolicyBlockedError):
        require_policy_allowed("blocked", decision)


# ---------------------------------------------------------------------------
# Approval state transitions

def test_approval_create_pending() -> None:
    service = ApprovalService()
    record = service.create(
        execution_id="exec-1",
        engagement_id="eng-1",
        effect="local_write",
        reason="needs approval",
    )
    assert record.state == "pending"
    assert record.is_pending is True
    assert record.is_terminal is False


def test_approval_grant_transition() -> None:
    service = ApprovalService()
    record = service.create(
        execution_id="exec-1", engagement_id="eng-1", effect="local_write"
    )
    granted = service.grant(record.id, decided_by="operator")
    assert granted.state == "granted"
    assert granted.is_granted is True
    assert granted.is_terminal is True
    assert granted.decided_by == "operator"


def test_approval_deny_transition() -> None:
    service = ApprovalService()
    record = service.create(
        execution_id="exec-1", engagement_id="eng-1", effect="local_write"
    )
    denied = service.deny(record.id, decided_by="operator", reason="denied")
    assert denied.state == "denied"
    assert denied.is_terminal is True


def test_approval_expire_transition() -> None:
    service = ApprovalService()
    record = service.create(
        execution_id="exec-1", engagement_id="eng-1", effect="local_write"
    )
    expired = service.expire(record.id)
    assert expired.state == "expired"
    assert expired.is_terminal is True


def test_approval_grant_twice_raises_conflict() -> None:
    service = ApprovalService()
    record = service.create(
        execution_id="exec-1", engagement_id="eng-1", effect="local_write"
    )
    service.grant(record.id, decided_by="operator")
    with pytest.raises(ConflictError):
        service.grant(record.id, decided_by="operator")


def test_approval_grant_unknown_raises_not_found() -> None:
    service = ApprovalService()
    with pytest.raises(NotFoundError):
        service.grant("no-such-approval", decided_by="operator")


def test_approval_service_policy_engine_integration() -> None:
    engine = PolicyEngine()
    approval = engine.create_approval(
        execution_id="exec-1",
        engagement_id="eng-1",
        effect="local_write",
        reason="sensitive effect",
    )
    assert approval.state == "pending"
    assert engine.is_approval_pending(approval.id) is True
    assert engine.is_approval_granted(approval.id) is False

    granted = engine.grant_approval(approval.id, decided_by="operator")
    assert granted.state == "granted"
    assert engine.is_approval_granted(approval.id) is True


def test_approval_state_literal_values() -> None:
    assert ApprovalState.__args__ == (  # type: ignore[attr-defined]
        "pending",
        "granted",
        "denied",
        "expired",
    )
