"""Dry-run planning: resolve inputs and display a sanitized plan.

A dry run resolves all inputs, validates scope and policy, and returns a plan
describing what would execute -- without launching any process.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DryRunPlan:
    """Sanitized execution plan produced by a dry run. No process is started."""

    execution_id: str
    action_id: str
    executable: str | None
    argv: list[str] = field(default_factory=list)
    outcome: str = ""
    reason: str | None = None
    scope_address: str | None = None
    effects: list[str] = field(default_factory=list)
    approval_required: bool = False
    timeout_seconds: int = 60
    max_output_bytes: int = 2_000_000
    decisions: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "executable": self.executable,
            "argv": list(self.argv),
            "outcome": self.outcome,
            "reason": self.reason,
            "scope_address": self.scope_address,
            "effects": list(self.effects),
            "approval_required": self.approval_required,
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "decisions": list(self.decisions),
            "dry_run": True,
        }


class DryRunPlanner:
    """Produces a :class:`DryRunPlan` from an execution and policy evaluation.

    Launches no process.
    """

    def plan(
        self,
        *,
        execution_id: str,
        action_id: str,
        executable: str | None,
        argv: list[str],
        outcome: str,
        reason: str | None,
        scope_address: str | None,
        effects: list[str],
        approval_required: bool,
        timeout_seconds: int,
        max_output_bytes: int,
        decisions: list[dict[str, object]],
    ) -> DryRunPlan:
        return DryRunPlan(
            execution_id=execution_id,
            action_id=action_id,
            executable=executable,
            argv=list(argv),
            outcome=outcome,
            reason=reason,
            scope_address=scope_address,
            effects=list(effects),
            approval_required=approval_required,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            decisions=list(decisions),
        )


__all__ = ["DryRunPlan", "DryRunPlanner"]
