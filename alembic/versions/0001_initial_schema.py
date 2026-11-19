"""Initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-19 00:00:00.000000
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engagements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "scope_id",
            sa.String(),
            sa.ForeignKey("scopes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_engagements"),
    )
    op.create_index("ix_engagements_name", "engagements", ["name"])
    op.create_index("ix_engagements_status", "engagements", ["status"])
    op.create_index("ix_engagements_scope_id", "engagements", ["scope_id"])

    op.create_table(
        "scopes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("include_hosts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("include_cidrs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("include_domains", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("exclude_hosts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("exclude_cidrs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_ports", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_requests_per_second", sa.Float(), nullable=True),
        sa.Column("allowed_effects", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("require_approval_for", sa.JSON(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id", name="pk_scopes"),
        sa.UniqueConstraint("engagement_id", name="uq_scopes_engagement_id"),
    )
    op.create_index("ix_scopes_engagement_id", "scopes", ["engagement_id"])

    op.create_table(
        "targets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False, server_default="host"),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_targets"),
        sa.UniqueConstraint(
            "engagement_id", "address", name="uq_targets_engagement_address"
        ),
    )
    op.create_index("ix_targets_engagement_id", "targets", ["engagement_id"])
    op.create_index("ix_targets_address", "targets", ["address"])
    op.create_index(
        "ix_targets_engagement_active", "targets", ["engagement_id", "is_active"]
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_id", sa.String(), nullable=True),
        sa.Column("preset_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("input_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("output_artifact_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.String(), nullable=False, server_default="operator"),
        sa.PrimaryKeyConstraint("id", name="pk_executions"),
    )
    op.create_index("ix_executions_engagement_id", "executions", ["engagement_id"])
    op.create_index("ix_executions_action_id", "executions", ["action_id"])
    op.create_index("ix_executions_status", "executions", ["status"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column(
            "source_execution_id",
            sa.String(),
            sa.ForeignKey("executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_ref", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("sensitivity", sa.String(length=20), nullable=False, server_default="internal"),
        sa.Column("secret_ref", sa.String(), nullable=True),
        sa.Column("scope_binding", sa.JSON(), nullable=True),
        sa.Column(
            "supersedes",
            sa.String(),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id", name="pk_artifacts"),
    )
    op.create_index("ix_artifacts_engagement_id", "artifacts", ["engagement_id"])
    op.create_index("ix_artifacts_type", "artifacts", ["type"])
    op.create_index("ix_artifacts_source_execution_id", "artifacts", ["source_execution_id"])
    op.create_index("ix_artifacts_target_ref", "artifacts", ["target_ref"])

    op.create_table(
        "execution_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "execution_id",
            sa.String(),
            sa.ForeignKey("executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_execution_events"),
    )
    op.create_index(
        "ix_execution_events_execution_id", "execution_events", ["execution_id"]
    )
    op.create_index(
        "ix_execution_events_execution_seq",
        "execution_events",
        ["execution_id", "sequence"],
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("target_ref", sa.String(), nullable=True),
        sa.Column("artifact_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_findings"),
    )
    op.create_index("ix_findings_engagement_id", "findings", ["engagement_id"])
    op.create_index("ix_findings_target_ref", "findings", ["target_ref"])

    op.create_table(
        "approval_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "execution_id",
            sa.String(),
            sa.ForeignKey("executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("effect", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_approval_records"),
    )
    op.create_index("ix_approval_records_engagement_id", "approval_records", ["engagement_id"])

    op.create_table(
        "evidence_metadata",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "engagement_id",
            sa.String(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "execution_id",
            sa.String(),
            sa.ForeignKey("executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("generated_id", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_metadata"),
        sa.UniqueConstraint("generated_id", name="uq_evidence_metadata_generated_id"),
    )
    op.create_index("ix_evidence_metadata_engagement_id", "evidence_metadata", ["engagement_id"])
    op.create_index("ix_evidence_metadata_generated_id", "evidence_metadata", ["generated_id"])


def downgrade() -> None:
    op.drop_table("evidence_metadata")
    op.drop_table("approval_records")
    op.drop_table("findings")
    op.drop_table("execution_events")
    op.drop_table("artifacts")
    op.drop_table("executions")
    op.drop_table("targets")
    op.drop_table("scopes")
    op.drop_table("engagements")
