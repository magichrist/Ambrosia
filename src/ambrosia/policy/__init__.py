"""Policy engine public interface.

Scope matching, effect classification, policy decision records, and approval
state management. Every action execution must pass through the policy engine
before any process is started.
"""

from __future__ import annotations

from ambrosia.policy.approvals import ApprovalRecord, ApprovalService, ApprovalState
from ambrosia.policy.decisions import DecisionOutcome, PolicyDecision, PolicyDecisionRecord
from ambrosia.policy.effects import EffectClassifier, EffectClassification, KNOWN_EFFECTS
from ambrosia.policy.engine import PolicyEngine, require_policy_allowed
from ambrosia.policy.scope import ScopeChecker, ScopeCheckResult

__all__ = [
    # scope
    "ScopeChecker",
    "ScopeCheckResult",
    # effects
    "EffectClassifier",
    "EffectClassification",
    "KNOWN_EFFECTS",
    # decisions
    "DecisionOutcome",
    "PolicyDecision",
    "PolicyDecisionRecord",
    # approvals
    "ApprovalRecord",
    "ApprovalService",
    "ApprovalState",
    # engine
    "PolicyEngine",
    "require_policy_allowed",
]
