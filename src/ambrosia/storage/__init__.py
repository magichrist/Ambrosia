"""Ambrosia storage layer: SQLite ORM models, repositories, evidence store,
and backup/export hooks.

ORM instances are private to this package. Repository APIs return domain
models (from ``ambrosia.domain.models``) or storage record dataclasses; they
never return ORM instances.
"""

from __future__ import annotations

from ambrosia.storage.backup import BackupHooks, ExportManifest, export_engagement_bundle
from ambrosia.storage.evidence import EvidenceStore
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
from ambrosia.storage.repositories import (
    ApprovalRecordRepository,
    ArtifactRepository,
    EngagementRepository,
    EvidenceRepository,
    ExecutionRepository,
    FindingRepository,
    ScopeRepository,
    TargetRepository,
)
from ambrosia.storage.session import (
    Storage,
    StorageConfig,
    create_engine_from_config,
    create_session_factory,
    drop_all,
    init_db,
    session_scope,
)

__all__ = [
    "Storage",
    "StorageConfig",
    "create_engine_from_config",
    "create_session_factory",
    "init_db",
    "drop_all",
    "session_scope",
    # ORM models (storage-internal; exported for alembic and tests only)
    "EngagementORM",
    "ScopeORM",
    "TargetORM",
    "ArtifactORM",
    "ExecutionORM",
    "ExecutionEventORM",
    "FindingORM",
    "ApprovalRecordORM",
    "EvidenceMetadataORM",
    # storage record dataclasses
    "TargetRecord",
    "FindingRecord",
    "ApprovalRecord",
    "EvidenceMetadataRecord",
    # repositories
    "EngagementRepository",
    "ScopeRepository",
    "ArtifactRepository",
    "ExecutionRepository",
    "TargetRepository",
    "FindingRepository",
    "ApprovalRecordRepository",
    "EvidenceRepository",
    # evidence store
    "EvidenceStore",
    # backup/export
    "BackupHooks",
    "ExportManifest",
    "export_engagement_bundle",
]
