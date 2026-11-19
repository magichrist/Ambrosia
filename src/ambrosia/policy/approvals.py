"""Approval state management for actions requiring approval.

The engine represents approval as an explicit state transition:

``pending`` -> ``granted`` | ``denied`` | ``expired``

v0.1 may use a CLI/TUI confirmation service to decide, but the engine must
represent approval as an explicit state transition rather than an implicit
check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from typing import Literal

from ambrosia.domain.errors import ConflictError, NotFoundError

ApprovalState = Literal["pending", "granted", "denied", "expired"]


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class ApprovalRecord:
    """A single approval decision tied to an execution and an effect."""

    id: str
    execution_id: str
    engagement_id: str
    effect: str
    state: ApprovalState = "pending"
    reason: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now_naive)

    @property
    def is_pending(self) -> bool:
        return self.state == "pending"

    @property
    def is_granted(self) -> bool:
        return self.state == "granted"

    @property
    def is_terminal(self) -> bool:
        return self.state in ("granted", "denied", "expired")


class ApprovalService:
    """Manages approval state transitions.

    Records are held in memory; the engine layer persists them through the
    storage repository when a database backend is in use.
    """

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    # ------------------------------------------------------------------ create

    def create(
        self,
        *,
        execution_id: str,
        engagement_id: str,
        effect: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        """Create a pending approval record."""
        import uuid

        record = ApprovalRecord(
            id=str(uuid.uuid4()),
            execution_id=execution_id,
            engagement_id=engagement_id,
            effect=effect,
            state="pending",
            reason=reason,
        )
        self._records[record.id] = record
        return record

    # ------------------------------------------------------------------ read

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    def get_for_execution(self, execution_id: str) -> list[ApprovalRecord]:
        return [
            record
            for record in self._records.values()
            if record.execution_id == execution_id
        ]

    # ------------------------------------------------------------------ transitions

    def grant(self, approval_id: str, *, decided_by: str) -> ApprovalRecord:
        """Transition ``pending`` -> ``granted``."""
        record = self._records.get(approval_id)
        if record is None:
            raise NotFoundError(f"approval record not found: {approval_id}")
        if not record.is_pending:
            raise ConflictError(
                f"approval {approval_id} is already {record.state}"
            )
        updated = ApprovalRecord(
            id=record.id,
            execution_id=record.execution_id,
            engagement_id=record.engagement_id,
            effect=record.effect,
            state="granted",
            reason=record.reason,
            decided_by=decided_by,
            decided_at=_utc_now_naive(),
            created_at=record.created_at,
        )
        self._records[updated.id] = updated
        return updated

    def deny(self, approval_id: str, *, decided_by: str, reason: str | None = None) -> ApprovalRecord:
        """Transition ``pending`` -> ``denied``."""
        record = self._records.get(approval_id)
        if record is None:
            raise NotFoundError(f"approval record not found: {approval_id}")
        if not record.is_pending:
            raise ConflictError(
                f"approval {approval_id} is already {record.state}"
            )
        updated = ApprovalRecord(
            id=record.id,
            execution_id=record.execution_id,
            engagement_id=record.engagement_id,
            effect=record.effect,
            state="denied",
            reason=reason or record.reason,
            decided_by=decided_by,
            decided_at=_utc_now_naive(),
            created_at=record.created_at,
        )
        self._records[updated.id] = updated
        return updated

    def expire(self, approval_id: str) -> ApprovalRecord:
        """Transition ``pending`` -> ``expired`` (e.g. operator timeout)."""
        record = self._records.get(approval_id)
        if record is None:
            raise NotFoundError(f"approval record not found: {approval_id}")
        if not record.is_pending:
            raise ConflictError(
                f"approval {approval_id} is already {record.state}"
            )
        updated = ApprovalRecord(
            id=record.id,
            execution_id=record.execution_id,
            engagement_id=record.engagement_id,
            effect=record.effect,
            state="expired",
            reason=record.reason,
            decided_by=None,
            decided_at=_utc_now_naive(),
            created_at=record.created_at,
        )
        self._records[updated.id] = updated
        return updated


__all__ = [
    "ApprovalRecord",
    "ApprovalService",
    "ApprovalState",
]
