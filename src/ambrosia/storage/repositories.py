"""Repository implementations matching the shared domain protocols.

Repositories accept a SQLAlchemy session and return domain models (or
storage record dataclasses). ORM instances never leave this module.
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ambrosia.domain.errors import NotFoundError
from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord, Scope
from ambrosia.storage.base import utc_now
from ambrosia.storage.evidence import EvidenceStore
from ambrosia.storage.converters import (
    approval_from_orm,
    artifact_from_orm,
    artifact_to_orm,
    engagement_from_orm,
    engagement_to_orm,
    evidence_metadata_from_orm,
    execution_from_orm,
    execution_to_orm,
    execution_event_to_orm,
    finding_from_orm,
    scope_from_orm,
    scope_to_orm,
    target_from_orm,
)
from ambrosia.storage.models import (
    ApprovalRecord,
    ApprovalRecordORM,
    ArtifactORM,
    EngagementORM,
    EvidenceMetadataORM,
    EvidenceMetadataRecord,
    ExecutionEventORM,
    ExecutionORM,
    FindingORM,
    FindingRecord,
    ScopeORM,
    TargetORM,
    TargetRecord,
)


class EngagementRepository:
    """Persistent engagements. Satisfies :class:`EngagementRepositoryProtocol`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, engagement_id: str) -> Engagement | None:
        orm = self.session.get(EngagementORM, engagement_id)
        return engagement_from_orm(orm) if orm is not None else None

    def create(self, engagement: Engagement) -> Engagement:
        orm = engagement_to_orm(engagement)
        self.session.add(orm)
        self.session.flush()
        return engagement_from_orm(orm)

    def list(self) -> list[Engagement]:
        statement = select(EngagementORM).order_by(EngagementORM.created_at)
        orms = self.session.execute(statement).scalars().all()
        return [engagement_from_orm(orm) for orm in orms]

    def update(self, engagement: Engagement) -> None:
        orm = self.session.get(EngagementORM, engagement.id)
        if orm is None:
            raise NotFoundError(f"engagement not found: {engagement.id}")
        orm.name = engagement.name
        orm.description = engagement.description
        orm.status = engagement.status
        orm.scope_id = engagement.scope_id
        orm.updated_at = engagement.updated_at
        self.session.flush()


class ScopeRepository:
    """Persistent scopes. Satisfies :class:`ScopeRepositoryProtocol`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, scope_id: str) -> Scope | None:
        orm = self.session.get(ScopeORM, scope_id)
        return scope_from_orm(orm) if orm is not None else None

    def create(self, scope: Scope) -> Scope:
        orm = scope_to_orm(scope)
        self.session.add(orm)
        self.session.flush()
        return scope_from_orm(orm)

    def get_for_engagement(self, engagement_id: str) -> Scope | None:
        statement = select(ScopeORM).where(ScopeORM.engagement_id == engagement_id)
        orm = self.session.execute(statement).scalar_one_or_none()
        return scope_from_orm(orm) if orm is not None else None

    def update(self, scope: Scope) -> None:
        orm = self.session.get(ScopeORM, scope.id)
        if orm is None:
            raise NotFoundError(f"scope not found: {scope.id}")
        orm.include_hosts = list(scope.include_hosts)
        orm.include_cidrs = list(scope.include_cidrs)
        orm.include_domains = list(scope.include_domains)
        orm.exclude_hosts = list(scope.exclude_hosts)
        orm.exclude_cidrs = list(scope.exclude_cidrs)
        orm.allowed_ports = list(scope.allowed_ports) if scope.allowed_ports is not None else None
        orm.expires_at = scope.expires_at
        orm.max_concurrency = scope.max_concurrency
        orm.max_requests_per_second = scope.max_requests_per_second
        orm.allowed_effects = list(scope.allowed_effects)
        orm.require_approval_for = list(scope.require_approval_for)
        self.session.flush()


class ArtifactRepository:
    """Persistent artifacts. Satisfies :class:`ArtifactRepositoryProtocol`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, artifact: Artifact) -> Artifact:
        orm = artifact_to_orm(artifact)
        self.session.add(orm)
        self.session.flush()
        return artifact_from_orm(orm)

    def get(self, artifact_id: str) -> Artifact | None:
        orm = self.session.get(ArtifactORM, artifact_id)
        return artifact_from_orm(orm) if orm is not None else None

    def list_for_engagement(self, engagement_id: str) -> list[Artifact]:
        statement = (
            select(ArtifactORM)
            .where(ArtifactORM.engagement_id == engagement_id)
            .order_by(ArtifactORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [artifact_from_orm(orm) for orm in orms]

    def list_by_target(self, target_ref: str) -> list[Artifact]:
        statement = (
            select(ArtifactORM)
            .where(ArtifactORM.target_ref == target_ref)
            .order_by(ArtifactORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [artifact_from_orm(orm) for orm in orms]


class ExecutionRepository:
    """Persistent executions. Satisfies :class:`ExecutionRepositoryProtocol`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, execution: ExecutionRecord) -> ExecutionRecord:
        orm = execution_to_orm(execution)
        self.session.add(orm)
        self.session.flush()
        return execution_from_orm(orm)

    def get(self, execution_id: str) -> ExecutionRecord | None:
        orm = self.session.get(ExecutionORM, execution_id)
        return execution_from_orm(orm) if orm is not None else None

    def list_for_engagement(self, engagement_id: str) -> list[ExecutionRecord]:
        statement = (
            select(ExecutionORM)
            .where(ExecutionORM.engagement_id == engagement_id)
            .order_by(ExecutionORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [execution_from_orm(orm) for orm in orms]

    def update(self, execution: ExecutionRecord) -> None:
        orm = self.session.get(ExecutionORM, execution.id)
        if orm is None:
            raise NotFoundError(f"execution not found: {execution.id}")
        orm.action_id = execution.action_id
        orm.preset_id = execution.preset_id
        orm.status = execution.status
        orm.started_at = execution.started_at
        orm.finished_at = execution.finished_at
        orm.target_refs = list(execution.target_refs)
        orm.input_summary = dict(execution.input_summary)
        orm.output_artifact_ids = list(execution.output_artifact_ids)
        orm.error_code = execution.error_code
        orm.error_message = execution.error_message
        orm.initiated_by = execution.initiated_by
        self.session.flush()

    def add_event(
        self, execution_id: str, kind: str, payload: dict[str, object], sequence: int
    ) -> None:
        orm = execution_event_to_orm(execution_id, kind, payload, sequence)
        self.session.add(orm)
        self.session.flush()

    def list_events(self, execution_id: str) -> list[dict[str, object]]:
        statement = (
            select(ExecutionEventORM)
            .where(ExecutionEventORM.execution_id == execution_id)
            .order_by(ExecutionEventORM.sequence)
        )
        orms = self.session.execute(statement).scalars().all()
        return [
            {
                "id": orm.id,
                "kind": orm.kind,
                "payload": dict(orm.payload),
                "timestamp": orm.timestamp,
                "sequence": orm.sequence,
            }
            for orm in orms
        ]


class TargetRepository:
    """Storage-specific target registry (not part of the shared protocols)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, target_id: str) -> TargetRecord | None:
        orm = self.session.get(TargetORM, target_id)
        return target_from_orm(orm) if orm is not None else None

    def create(
        self,
        *,
        engagement_id: str,
        address: str,
        target_type: str = "host",
        hostname: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
    ) -> TargetRecord:
        orm = TargetORM(
            engagement_id=engagement_id,
            address=address,
            target_type=target_type,
            hostname=hostname,
            notes=notes,
            is_active=is_active,
            created_at=utc_now(),
        )
        self.session.add(orm)
        self.session.flush()
        return target_from_orm(orm)

    def list_for_engagement(self, engagement_id: str) -> list[TargetRecord]:
        statement = (
            select(TargetORM)
            .where(TargetORM.engagement_id == engagement_id)
            .order_by(TargetORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [target_from_orm(orm) for orm in orms]


class FindingRepository:
    """Storage-specific finding registry (not part of the shared protocols)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        engagement_id: str,
        title: str,
        severity: str,
        description: str | None = None,
        target_ref: str | None = None,
        artifact_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> FindingRecord:
        orm = FindingORM(
            engagement_id=engagement_id,
            title=title,
            description=description,
            severity=severity,
            target_ref=target_ref,
            artifact_refs=list(artifact_refs or []),
            evidence_refs=list(evidence_refs or []),
            created_at=utc_now() if created_at is None else created_at,
        )
        self.session.add(orm)
        self.session.flush()
        return finding_from_orm(orm)

    def get(self, finding_id: str) -> FindingRecord | None:
        orm = self.session.get(FindingORM, finding_id)
        return finding_from_orm(orm) if orm is not None else None

    def list_for_engagement(self, engagement_id: str) -> list[FindingRecord]:
        statement = (
            select(FindingORM)
            .where(FindingORM.engagement_id == engagement_id)
            .order_by(FindingORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [finding_from_orm(orm) for orm in orms]


class ApprovalRecordRepository:
    """Storage-specific approval record registry (not part of the shared protocols)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        engagement_id: str,
        effect: str,
        decision: str = "pending",
        execution_id: str | None = None,
        reason: str | None = None,
        decided_by: str | None = None,
        decided_at: datetime | None = None,
    ) -> ApprovalRecord:
        orm = ApprovalRecordORM(
            engagement_id=engagement_id,
            execution_id=execution_id,
            effect=effect,
            reason=reason,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            created_at=utc_now(),
        )
        self.session.add(orm)
        self.session.flush()
        return approval_from_orm(orm)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        orm = self.session.get(ApprovalRecordORM, approval_id)
        return approval_from_orm(orm) if orm is not None else None

    def list_for_engagement(self, engagement_id: str) -> list[ApprovalRecord]:
        statement = (
            select(ApprovalRecordORM)
            .where(ApprovalRecordORM.engagement_id == engagement_id)
            .order_by(ApprovalRecordORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [approval_from_orm(orm) for orm in orms]

    def update_decision(
        self,
        approval_id: str,
        *,
        decision: str,
        decided_by: str | None = None,
        decided_at: datetime | None = None,
    ) -> None:
        orm = self.session.get(ApprovalRecordORM, approval_id)
        if orm is None:
            raise NotFoundError(f"approval record not found: {approval_id}")
        orm.decision = decision
        orm.decided_by = decided_by
        orm.decided_at = decided_at
        self.session.flush()


class EvidenceRepository:
    """Storage-specific evidence metadata registry (not part of the shared protocols)."""

    def __init__(self, session: Session, store: EvidenceStore | None = None) -> None:
        self.session = session
        self.store = store or EvidenceStore()

    def record_file(
        self,
        source_path: str | os.PathLike[str],
        *,
        engagement_id: str,
        execution_id: str | None = None,
        media_type: str | None = None,
    ) -> EvidenceMetadataRecord:
        """Store an evidence file and persist its metadata.

        The file is written under a generated ID; the database keeps only
        metadata and the generated relative path.
        """
        info = self.store.store_file(source_path)
        orm = EvidenceMetadataORM(
            engagement_id=engagement_id,
            execution_id=execution_id,
            generated_id=info["generated_id"],
            relative_path=info["relative_path"],
            filename=info["filename"],
            content_hash=info["content_hash"],
            media_type=media_type,
            size=info["size"],
            created_at=utc_now(),
        )
        self.session.add(orm)
        self.session.flush()
        return evidence_metadata_from_orm(orm)

    def get(self, evidence_id: str) -> EvidenceMetadataRecord | None:
        orm = self.session.get(EvidenceMetadataORM, evidence_id)
        return evidence_metadata_from_orm(orm) if orm is not None else None

    def list_for_engagement(self, engagement_id: str) -> list[EvidenceMetadataRecord]:
        statement = (
            select(EvidenceMetadataORM)
            .where(EvidenceMetadataORM.engagement_id == engagement_id)
            .order_by(EvidenceMetadataORM.created_at)
        )
        orms = self.session.execute(statement).scalars().all()
        return [evidence_metadata_from_orm(orm) for orm in orms]

    def list_by_generated_id(self, generated_id: str) -> EvidenceMetadataRecord | None:
        statement = select(EvidenceMetadataORM).where(
            EvidenceMetadataORM.generated_id == generated_id
        )
        orm = self.session.execute(statement).scalar_one_or_none()
        return evidence_metadata_from_orm(orm) if orm is not None else None
