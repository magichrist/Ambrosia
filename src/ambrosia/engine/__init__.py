"""Execution engine public interface.

Job lifecycle, concurrency limits, timeouts, cancellation, and dry-run planning.
Every job has an ID and durable status transitions through the execution
repository.
"""

from __future__ import annotations

from ambrosia.engine.dry_run import DryRunPlan, DryRunPlanner
from ambrosia.engine.engine import JobEngine
from ambrosia.engine.job import JobEvent, JobStatus, valid_transition

__all__ = [
    "DryRunPlan",
    "DryRunPlanner",
    "JobEngine",
    "JobEvent",
    "JobStatus",
    "valid_transition",
]
