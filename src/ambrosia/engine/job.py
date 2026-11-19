"""Execution lifecycle state machine.

Every job has an ID and durable status transitions:

``draft`` -> ``validated`` -> ``awaiting_input`` | ``awaiting_approval`` ->
``ready`` -> ``running`` -> ``parsing`` -> ``succeeded`` | ``partial`` |
``failed`` | ``cancelled`` | ``blocked``
"""

from __future__ import annotations

from dataclasses import dataclass

from ambrosia.domain.models import ExecutionStatus

JobStatus = ExecutionStatus


@dataclass(frozen=True)
class JobEvent:
    """A durable state-transition event for a job."""

    execution_id: str
    from_status: JobStatus | None
    to_status: JobStatus
    reason: str | None = None
    timestamp: str | None = None


# Valid transitions: from -> set of allowed to-statuses.
_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    "draft": {"validated", "blocked"},
    "validated": {"awaiting_input", "awaiting_approval", "ready", "blocked"},
    "awaiting_input": {"validated", "ready", "blocked"},
    "awaiting_approval": {"ready", "blocked", "cancelled"},
    "ready": {"running", "blocked", "cancelled"},
    "running": {"parsing", "failed", "cancelled", "blocked"},
    "parsing": {"succeeded", "partial", "failed", "cancelled"},
    "succeeded": set(),
    "partial": set(),
    "failed": set(),
    "cancelled": set(),
    "blocked": set(),
}


def valid_transition(from_status: JobStatus, to_status: JobStatus) -> bool:
    """Return whether ``from_status -> to_status`` is a legal lifecycle move."""
    return to_status in _VALID_TRANSITIONS.get(from_status, set())


__all__ = ["JobEvent", "JobStatus", "valid_transition"]
