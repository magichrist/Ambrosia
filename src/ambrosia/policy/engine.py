"""Policy engine: scope + effects + approvals combined.

Used at execution time to enforce policy before any process starts. Every
action execution produces a :class:`~ambrosia.policy.decisions.PolicyDecision`
record. No action may launch without a valid policy evaluation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.domain.errors import PolicyBlockedError, ScopeViolationError
from ambrosia.policy.approvals import ApprovalRecord, ApprovalService
from ambrosia.policy.decisions import PolicyDecision, PolicyDecisionRecord
from ambrosia.policy.effects import EffectClassifier
from ambrosia.policy.scope import ScopeChecker

if TYPE_CHECKING:
    from ambrosia.domain.action import ActionDefinition
    from ambrosia.domain.models import Scope


class PolicyEngine:
    """Combines scope checking, effect classification, and approval state.

    The engine is the single enforcement point: ``evaluate`` must be called
    for every execution path (CLI, TUI, presets, plugins) before any process
    is started.
    """

    def __init__(
        self,
        *,
        scope_checker: ScopeChecker | None = None,
        effect_classifier: EffectClassifier | None = None,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._scope = scope_checker or ScopeChecker()
        self._effects = effect_classifier or EffectClassifier()
        self._approvals = approval_service or ApprovalService()

    # ------------------------------------------------------------------ evaluate

    def evaluate(
        self,
        *,
        action: ActionDefinition,
        scope: Scope,
        address: str | None = None,
        port: int | None = None,
        execution_id: str | None = None,
        engagement_id: str | None = None,
    ) -> tuple[str, PolicyDecision, PolicyDecisionRecord]:
        """Evaluate an action against policy.

        Returns ``(outcome, primary_decision, record)`` where ``outcome`` is
        one of ``"allowed"``, ``"blocked"``, or ``"requires_approval"``.

        Raises :class:`~ambrosia.domain.errors.ScopeViolationError` when the
        target is outside scope (this is a hard block, not a soft decision).
        """
        record = PolicyDecisionRecord(execution_id=execution_id or "")

        # --- Scope check ---------------------------------------------------
        scope_decision: PolicyDecision | None = None
        if address is not None and action.scope_fields:
            try:
                self._scope.check_target(address, port=port, scope=scope)
                scope_decision = PolicyDecision(
                    execution_id=execution_id or "",
                    action_id=action.id,
                    engagement_id=engagement_id or "",
                    outcome="allowed",
                    reason="scope check passed",
                    scope_address=address,
                    scope_in_scope=True,
                )
            except ScopeViolationError as exc:
                scope_decision = PolicyDecision(
                    execution_id=execution_id or "",
                    action_id=action.id,
                    engagement_id=engagement_id or "",
                    outcome="blocked",
                    reason=exc.message,
                    scope_address=address,
                    scope_in_scope=False,
                )
                record = record.add(scope_decision)
                return "blocked", scope_decision, record

            record = record.add(scope_decision)

        # --- Effect classification ----------------------------------------
        classification = self._effects.classify(
            list(action.effects),
            allowed_effects=frozenset(scope.allowed_effects),
            require_approval_for=frozenset(scope.require_approval_for),
        )

        if classification.blocked:
            reason = "effects not allowed by scope: " + ", ".join(sorted(classification.blocked))
            decision = PolicyDecision(
                execution_id=execution_id or "",
                action_id=action.id,
                engagement_id=engagement_id or "",
                outcome="blocked",
                reason=reason,
                effects_blocked=classification.blocked,
            )
            record = record.add(decision)
            return "blocked", decision, record

        if classification.requires_approval:
            reason = "approval required for effects: " + ", ".join(
                sorted(classification.requires_approval)
            )
            decision = PolicyDecision(
                execution_id=execution_id or "",
                action_id=action.id,
                engagement_id=engagement_id or "",
                outcome="requires_approval",
                reason=reason,
                effects_requires_approval=classification.requires_approval,
            )
            record = record.add(decision)
            return "requires_approval", decision, record

        decision = PolicyDecision(
            execution_id=execution_id or "",
            action_id=action.id,
            engagement_id=engagement_id or "",
            outcome="allowed",
            reason="all policy checks passed",
            effects_allowed=classification.allowed,
        )
        record = record.add(decision)
        return "allowed", decision, record

    # ------------------------------------------------------------------ approvals

    def create_approval(
        self,
        *,
        execution_id: str,
        engagement_id: str,
        effect: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        """Create a pending approval record for an execution."""
        return self._approvals.create(
            execution_id=execution_id,
            engagement_id=engagement_id,
            effect=effect,
            reason=reason,
        )

    def grant_approval(self, approval_id: str, *, decided_by: str) -> ApprovalRecord:
        return self._approvals.grant(approval_id, decided_by=decided_by)

    def deny_approval(
        self, approval_id: str, *, decided_by: str, reason: str | None = None
    ) -> ApprovalRecord:
        return self._approvals.deny(approval_id, decided_by=decided_by, reason=reason)

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        return self._approvals.get(approval_id)

    def is_approval_granted(self, approval_id: str) -> bool:
        record = self._approvals.get(approval_id)
        return record is not None and record.is_granted

    def is_approval_pending(self, approval_id: str) -> bool:
        record = self._approvals.get(approval_id)
        return record is not None and record.is_pending


def require_policy_allowed(outcome: str, decision: PolicyDecision) -> None:
    """Raise :class:`~ambrosia.domain.errors.PolicyBlockedError` unless allowed.

    Convenience helper for execution paths that must fail fast when policy
    blocks an action.
    """

    if outcome != "allowed":
        raise PolicyBlockedError(
            decision.reason or "execution blocked by policy",
            details={
                "outcome": outcome,
                "action_id": decision.action_id,
                "execution_id": decision.execution_id,
            },
        )


__all__ = [
    "PolicyEngine",
    "require_policy_allowed",
]
