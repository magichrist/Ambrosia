"""Policy decision records.

Durable, auditable records of policy enforcement decisions made at execution
time. Every execution path produces at least one decision record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


DecisionOutcome = str  # "allowed" | "blocked" | "requires_approval"


@dataclass(frozen=True)
class PolicyDecision:
    """A single policy enforcement decision for one action execution."""

    execution_id: str
    action_id: str
    engagement_id: str
    outcome: DecisionOutcome
    reason: str | None = None
    scope_address: str | None = None
    scope_in_scope: bool | None = None
    effects_allowed: tuple[str, ...] = field(default_factory=tuple)
    effects_blocked: tuple[str, ...] = field(default_factory=tuple)
    effects_requires_approval: tuple[str, ...] = field(default_factory=tuple)
    decided_at: datetime = field(default_factory=_utc_now_naive)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a safe, secret-free dictionary for logging/storage."""
        return {
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "engagement_id": self.engagement_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "scope_address": self.scope_address,
            "scope_in_scope": self.scope_in_scope,
            "effects_allowed": list(self.effects_allowed),
            "effects_blocked": list(self.effects_blocked),
            "effects_requires_approval": list(self.effects_requires_approval),
            "decided_at": self.decided_at.isoformat(),
        }


@dataclass(frozen=True)
class PolicyDecisionRecord:
    """Durable record of all policy decisions for an execution."""

    execution_id: str
    decisions: tuple[PolicyDecision, ...] = field(default_factory=tuple)

    def add(self, decision: PolicyDecision) -> PolicyDecisionRecord:
        """Return a new record with ``decision`` appended (immutable)."""
        return PolicyDecisionRecord(
            execution_id=self.execution_id,
            decisions=(*self.decisions, decision),
        )

    def to_list(self) -> list[dict[str, object]]:
        return [d.to_dict() for d in self.decisions]

    @property
    def blocked(self) -> bool:
        return any(d.outcome == "blocked" for d in self.decisions)

    @property
    def requires_approval(self) -> bool:
        return any(d.outcome == "requires_approval" for d in self.decisions)

    @property
    def allowed(self) -> bool:
        return all(d.outcome == "allowed" for d in self.decisions) and bool(self.decisions)


__all__ = ["DecisionOutcome", "PolicyDecision", "PolicyDecisionRecord"]
