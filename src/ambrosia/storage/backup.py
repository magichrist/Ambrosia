"""Backup/export hooks for engagement bundles.

An engagement bundle serializes engagement, scope, artifacts, executions,
events, findings, approvals, and evidence metadata into JSON. Secret values
are never exported: only opaque references (``secret_ref``) may appear, and
domain validation guarantees artifact values and execution summaries contain
no raw secret material.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ambrosia.domain.errors import NotFoundError
from ambrosia.storage.base import from_storage_dt
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

if TYPE_CHECKING:
    import os
    from collections.abc import Callable

    from ambrosia.storage.session import Storage


@dataclass(frozen=True)
class ExportManifest:
    """Result of exporting an engagement bundle."""

    engagement_id: str
    bundle_path: str
    created_at: str
    artifact_count: int
    execution_count: int
    finding_count: int
    evidence_files: list[str]
    sha256: str


class BackupHooks:
    """Registrable callbacks invoked around an export."""

    def __init__(self) -> None:
        self._pre: list[Callable[[str], None]] = []
        self._post: list[Callable[[ExportManifest], None]] = []

    def register_pre(self, hook: Callable[[str], None]) -> None:
        self._pre.append(hook)

    def register_post(self, hook: Callable[[ExportManifest], None]) -> None:
        self._post.append(hook)

    def run_pre(self, engagement_id: str) -> None:
        for hook in self._pre:
            hook(engagement_id)

    def run_post(self, manifest: ExportManifest) -> None:
        for hook in self._post:
            hook(manifest)


def _isoformat(value: datetime | None) -> str | None:
    """Format a stored datetime as ISO 8601, or None when absent."""
    return value.isoformat() if value is not None else None


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set):
        # Pydantic model_dump() emits set-typed fields as Python sets; JSON
        # has no set type. Serialise as a sorted list for deterministic output.
        return sorted(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def export_engagement_bundle(
    storage: Storage,
    engagement_id: str,
    output_dir: str | os.PathLike[str],
    *,
    include_evidence_files: bool = True,
    hooks: BackupHooks | None = None,
) -> ExportManifest:
    """Export an engagement bundle without secret values.

    Writes ``bundle.json`` (and optionally a zip of evidence files) into
    ``output_dir`` and returns an :class:`ExportManifest`.
    """
    hooks = hooks or BackupHooks()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    hooks.run_pre(engagement_id)

    with storage.session() as session:
        engagement = EngagementRepository(session).get(engagement_id)
        if engagement is None:
            raise NotFoundError(f"engagement not found: {engagement_id}")
        scope = ScopeRepository(session).get_for_engagement(engagement_id)
        targets = TargetRepository(session).list_for_engagement(engagement_id)
        artifacts = ArtifactRepository(session).list_for_engagement(engagement_id)
        executions = ExecutionRepository(session).list_for_engagement(engagement_id)
        events_by_execution = {
            execution.id: ExecutionRepository(session).list_events(execution.id)
            for execution in executions
        }
        findings = FindingRepository(session).list_for_engagement(engagement_id)
        approvals = ApprovalRecordRepository(session).list_for_engagement(engagement_id)
        evidence = EvidenceRepository(session).list_for_engagement(engagement_id)

    bundle: dict[str, Any] = {
        "engagement": engagement.model_dump(),
        "scope": scope.model_dump() if scope is not None else None,
        "targets": [
            {
                "id": t.id,
                "address": t.address,
                "target_type": t.target_type,
                "hostname": t.hostname,
                "is_active": t.is_active,
                "created_at": _isoformat(from_storage_dt(t.created_at)),
            }
            for t in targets
        ],
        "artifacts": [artifact.model_dump() for artifact in artifacts],
        "executions": [execution.model_dump() for execution in executions],
        "execution_events": dict(events_by_execution.items()),
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "target_ref": f.target_ref,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in findings
        ],
        "approvals": [
            {
                "id": a.id,
                "effect": a.effect,
                "decision": a.decision,
                "created_at": _isoformat(from_storage_dt(a.created_at)),
            }
            for a in approvals
        ],
        "evidence_metadata": [
            {
                "id": e.id,
                "generated_id": e.generated_id,
                "relative_path": e.relative_path,
                "filename": e.filename,
                "content_hash": e.content_hash,
                "media_type": e.media_type,
                "size": e.size,
                "created_at": _isoformat(from_storage_dt(e.created_at)),
            }
            for e in evidence
        ],
    }

    evidence_files: list[str] = []
    if include_evidence_files:
        evidence_zip = output_dir / f"{engagement_id}_evidence.zip"
        with zipfile.ZipFile(evidence_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in evidence:
                file_path = storage.evidence.path_for(item.relative_path)
                if file_path.is_file():
                    archive.write(file_path, arcname=f"evidence/{item.relative_path}")
                    evidence_files.append(str(evidence_zip.name))
        # Relative path stored in manifest; bundle references evidence files by name.
        bundle["evidence_files"] = evidence_files

    bundle_path = output_dir / f"{engagement_id}_bundle.json"
    bundle_text = json.dumps(bundle, indent=2, sort_keys=True, default=_json_default)
    bundle_path.write_text(bundle_text, encoding="utf-8")
    sha256 = hashlib.sha256(bundle_text.encode("utf-8")).hexdigest()

    manifest = ExportManifest(
        engagement_id=engagement_id,
        bundle_path=str(bundle_path),
        created_at=datetime.now(UTC).isoformat(),
        artifact_count=len(artifacts),
        execution_count=len(executions),
        finding_count=len(findings),
        evidence_files=evidence_files,
        sha256=sha256,
    )

    hooks.run_post(manifest)
    return manifest
