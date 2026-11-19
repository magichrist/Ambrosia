"""ORM row <-> domain model converters.

This is the only place where ORM instances are translated into domain models.
Domain packages never import ORM classes, and ORM instances never escape the
storage package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from ambrosia.domain.models import (
    Artifact,
    Engagement,
    ExecutionRecord,
    Scope,
)
from ambrosia.storage.base import from_storage_dt, to_storage_dt, utc_now
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

if TYPE_CHECKING:
    from datetime import datetime

_EngagementStatus = Literal["active", "paused", "archived"]
_ArtifactSourceKind = Literal["action", "preset", "operator", "import"]
_ArtifactSensitivity = Literal["public", "internal", "sensitive", "secret"]
_ExecutionStatus = Literal[
    "draft",
    "validated",
    "awaiting_input",
    "awaiting_approval",
    "ready",
    "running",
    "parsing",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "blocked",
]


def engagement_to_orm(engagement: Engagement) -> EngagementORM:
    return EngagementORM(
        id=engagement.id,
        name=engagement.name,
        description=engagement.description,
        status=engagement.status,
        created_at=to_storage_dt(engagement.created_at),
        updated_at=to_storage_dt(engagement.updated_at),
        scope_id=engagement.scope_id,
    )


def engagement_from_orm(orm: EngagementORM) -> Engagement:
    return Engagement(
        id=orm.id,
        name=orm.name,
        description=orm.description,
        status=cast("_EngagementStatus", orm.status),
        created_at=cast("datetime", from_storage_dt(orm.created_at)),
        updated_at=cast("datetime", from_storage_dt(orm.updated_at)),
        scope_id=orm.scope_id,
    )


def scope_to_orm(scope: Scope) -> ScopeORM:
    return ScopeORM(
        id=scope.id,
        engagement_id=scope.engagement_id,
        include_hosts=list(scope.include_hosts),
        include_cidrs=list(scope.include_cidrs),
        include_domains=list(scope.include_domains),
        exclude_hosts=list(scope.exclude_hosts),
        exclude_cidrs=list(scope.exclude_cidrs),
        allowed_ports=list(scope.allowed_ports) if scope.allowed_ports is not None else None,
        expires_at=to_storage_dt(scope.expires_at) if scope.expires_at is not None else None,
        max_concurrency=scope.max_concurrency,
        max_requests_per_second=scope.max_requests_per_second,
        allowed_effects=list(scope.allowed_effects),
        require_approval_for=list(scope.require_approval_for),
    )


def scope_from_orm(orm: ScopeORM) -> Scope:
    return Scope(
        id=orm.id,
        engagement_id=orm.engagement_id,
        include_hosts=list(orm.include_hosts),
        include_cidrs=list(orm.include_cidrs),
        include_domains=list(orm.include_domains),
        exclude_hosts=list(orm.exclude_hosts),
        exclude_cidrs=list(orm.exclude_cidrs),
        allowed_ports=list(orm.allowed_ports) if orm.allowed_ports is not None else None,
        expires_at=from_storage_dt(orm.expires_at),
        max_concurrency=orm.max_concurrency,
        max_requests_per_second=orm.max_requests_per_second,
        allowed_effects=set(orm.allowed_effects),
        require_approval_for=set(orm.require_approval_for),
    )


def artifact_to_orm(artifact: Artifact) -> ArtifactORM:
    return ArtifactORM(
        id=artifact.id,
        engagement_id=artifact.engagement_id,
        type=artifact.type,
        value=dict(artifact.value),
        source_kind=artifact.source_kind,
        source_id=artifact.source_id,
        source_execution_id=artifact.source_execution_id,
        target_ref=artifact.target_ref,
        created_at=to_storage_dt(artifact.created_at),
        confidence=artifact.confidence,
        sensitivity=artifact.sensitivity,
        secret_ref=artifact.secret_ref,
        scope_binding=dict(artifact.scope_binding) if artifact.scope_binding is not None else None,
        supersedes=artifact.supersedes,
        expires_at=to_storage_dt(artifact.expires_at) if artifact.expires_at is not None else None,
        artifact_metadata=dict(artifact.metadata),
    )


def artifact_from_orm(orm: ArtifactORM) -> Artifact:
    return Artifact(
        id=orm.id,
        engagement_id=orm.engagement_id,
        type=orm.type,
        value=dict(orm.value) if orm.value else {},
        source_kind=cast("_ArtifactSourceKind", orm.source_kind),
        source_id=orm.source_id,
        source_execution_id=orm.source_execution_id,
        target_ref=orm.target_ref,
        created_at=cast("datetime", from_storage_dt(orm.created_at)),
        confidence=orm.confidence,
        sensitivity=cast("_ArtifactSensitivity", orm.sensitivity),
        secret_ref=orm.secret_ref,
        scope_binding=dict(orm.scope_binding) if orm.scope_binding is not None else None,
        supersedes=orm.supersedes,
        expires_at=from_storage_dt(orm.expires_at),
        metadata=dict(orm.artifact_metadata) if orm.artifact_metadata else {},
    )


def execution_to_orm(execution: ExecutionRecord) -> ExecutionORM:
    return ExecutionORM(
        id=execution.id,
        engagement_id=execution.engagement_id,
        action_id=execution.action_id,
        preset_id=execution.preset_id,
        created_at=utc_now(),
        status=execution.status,
        started_at=to_storage_dt(execution.started_at) if execution.started_at is not None else None,
        finished_at=to_storage_dt(execution.finished_at) if execution.finished_at is not None else None,
        target_refs=list(execution.target_refs),
        input_summary=dict(execution.input_summary),
        output_artifact_ids=list(execution.output_artifact_ids),
        error_code=execution.error_code,
        error_message=execution.error_message,
        initiated_by=execution.initiated_by,
    )


def execution_from_orm(orm: ExecutionORM) -> ExecutionRecord:
    return ExecutionRecord(
        id=orm.id,
        engagement_id=orm.engagement_id,
        action_id=orm.action_id,
        preset_id=orm.preset_id,
        status=cast("_ExecutionStatus", orm.status),
        started_at=from_storage_dt(orm.started_at),
        finished_at=from_storage_dt(orm.finished_at),
        target_refs=list(orm.target_refs),
        input_summary=dict(orm.input_summary),
        output_artifact_ids=list(orm.output_artifact_ids),
        error_code=orm.error_code,
        error_message=orm.error_message,
        initiated_by=orm.initiated_by,
    )


def execution_event_to_orm(execution_id: str, kind: str, payload: dict[str, object], sequence: int) -> ExecutionEventORM:
    return ExecutionEventORM(
        execution_id=execution_id,
        kind=kind,
        payload=dict(payload),
        timestamp=utc_now(),
        sequence=sequence,
    )



def target_from_orm(orm: TargetORM) -> TargetRecord:
    return TargetRecord(
        id=orm.id,
        engagement_id=orm.engagement_id,
        address=orm.address,
        target_type=orm.target_type,
        hostname=orm.hostname,
        notes=orm.notes,
        is_active=bool(orm.is_active),
        created_at=cast("datetime", from_storage_dt(orm.created_at)),
    )


def finding_from_orm(orm: FindingORM) -> FindingRecord:
    return FindingRecord(
        id=orm.id,
        engagement_id=orm.engagement_id,
        title=orm.title,
        description=orm.description,
        severity=orm.severity,
        status=orm.status,
        target_ref=orm.target_ref,
        artifact_refs=list(orm.artifact_refs),
        evidence_refs=list(orm.evidence_refs),
        created_at=cast("datetime", from_storage_dt(orm.created_at)),
    )


def approval_from_orm(orm: ApprovalRecordORM) -> ApprovalRecord:
    return ApprovalRecord(
        id=orm.id,
        engagement_id=orm.engagement_id,
        execution_id=orm.execution_id,
        effect=orm.effect,
        reason=orm.reason,
        decision=orm.decision,
        decided_by=orm.decided_by,
        decided_at=from_storage_dt(orm.decided_at),
        created_at=cast("datetime", from_storage_dt(orm.created_at)),
    )


def evidence_metadata_from_orm(orm: EvidenceMetadataORM) -> EvidenceMetadataRecord:
    return EvidenceMetadataRecord(
        id=orm.id,
        engagement_id=orm.engagement_id,
        execution_id=orm.execution_id,
        generated_id=orm.generated_id,
        relative_path=orm.relative_path,
        filename=orm.filename,
        content_hash=orm.content_hash,
        media_type=orm.media_type,
        size=orm.size,
        created_at=cast("datetime", from_storage_dt(orm.created_at)),
    )



