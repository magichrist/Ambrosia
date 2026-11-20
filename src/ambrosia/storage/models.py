"""SQLAlchemy ORM models for Ambrosia storage.

ORM instances are private to the storage package. Repository boundaries
convert ORM rows into domain models (see ``converters.py``); ORM instances
must never escape into domain, UI, or application packages.

The ``*Record`` dataclasses are lightweight read models returned by
storage-specific repository methods; they are not ORM instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 - SQLAlchemy resolves Mapped[] annotations at runtime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ambrosia.storage.base import Base, JSONType, utc_now


def _new_id() -> str:
    return str(uuid4())


class EngagementORM(Base):
    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    scope_id: Mapped[str | None] = mapped_column(
        ForeignKey("scopes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    scope: Mapped[ScopeORM | None] = relationship(
        "ScopeORM",
        uselist=False,
        primaryjoin="foreign(EngagementORM.scope_id)==ScopeORM.id",
    )
    artifacts: Mapped[list[ArtifactORM]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    executions: Mapped[list[ExecutionORM]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    targets: Mapped[list[TargetORM]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    findings: Mapped[list[FindingORM]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[ApprovalRecordORM]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    evidence: Mapped[list[EvidenceMetadataORM]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )


class ScopeORM(Base):
    __tablename__ = "scopes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    include_hosts: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    include_cidrs: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    include_domains: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    exclude_hosts: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    exclude_cidrs: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    allowed_ports: Mapped[list[int] | None] = mapped_column(JSONType, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_requests_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    allowed_effects: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    require_approval_for: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )

    engagement: Mapped[EngagementORM] = relationship(
        "EngagementORM",
        primaryjoin="foreign(ScopeORM.engagement_id)==EngagementORM.id",
    )


class TargetORM(Base):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, default="host")
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "engagement_id", "address", name="uq_targets_engagement_address"
        ),
        Index("ix_targets_engagement_active", "engagement_id", "is_active"),
    )

    engagement: Mapped[EngagementORM] = relationship(back_populates="targets")


class ArtifactORM(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_ref: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sensitivity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="internal"
    )
    secret_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    scope_binding: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    supersedes: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "metadata" is reserved by SQLAlchemy's declarative base; keep the DB
    # column name "metadata" via name= while using a safe Python attribute.
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False, name="metadata"
    )

    execution: Mapped[ExecutionORM | None] = relationship(
        back_populates="artifacts", foreign_keys=[source_execution_id]
    )
    engagement: Mapped[EngagementORM] = relationship(back_populates="artifacts")


class ExecutionORM(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    preset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    target_refs: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    input_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    output_artifact_ids: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_by: Mapped[str] = mapped_column(String, nullable=False, default="operator")

    events: Mapped[list[ExecutionEventORM]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ExecutionEventORM.sequence",
    )
    artifacts: Mapped[list[ArtifactORM]] = relationship(
        back_populates="execution", foreign_keys=[ArtifactORM.source_execution_id]
    )
    engagement: Mapped[EngagementORM] = relationship(back_populates="executions")


class ExecutionEventORM(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_execution_events_execution_seq", "execution_id", "sequence"),
    )

    execution: Mapped[ExecutionORM] = relationship(back_populates="events")


class FindingORM(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    target_ref: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    artifact_refs: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    evidence_refs: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    engagement: Mapped[EngagementORM] = relationship(back_populates="findings")


class ApprovalRecordORM(Base):
    __tablename__ = "approval_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"), nullable=True
    )
    effect: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    engagement: Mapped[EngagementORM] = relationship(back_populates="approvals")


class EvidenceMetadataORM(Base):
    __tablename__ = "evidence_metadata"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"), nullable=True
    )
    generated_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    engagement: Mapped[EngagementORM] = relationship(back_populates="evidence")


@dataclass(frozen=True)
class TargetRecord:
    id: str
    engagement_id: str
    address: str
    target_type: str
    hostname: str | None
    notes: str | None
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class FindingRecord:
    id: str
    engagement_id: str
    title: str
    description: str | None
    severity: str
    status: str
    target_ref: str | None
    artifact_refs: list[str]
    evidence_refs: list[str]
    created_at: datetime


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    engagement_id: str
    execution_id: str | None
    effect: str
    reason: str | None
    decision: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class EvidenceMetadataRecord:
    id: str
    engagement_id: str
    execution_id: str | None
    generated_id: str
    relative_path: str
    filename: str
    content_hash: str
    media_type: str | None
    size: int
    created_at: datetime


__all__ = [
    "EngagementORM",
    "ScopeORM",
    "TargetORM",
    "ArtifactORM",
    "ExecutionORM",
    "ExecutionEventORM",
    "FindingORM",
    "ApprovalRecordORM",
    "EvidenceMetadataORM",
    "TargetRecord",
    "FindingRecord",
    "ApprovalRecord",
    "EvidenceMetadataRecord",
]
