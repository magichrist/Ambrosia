"""Engagement bundle export: no secret values leave the store."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ambrosia.domain.errors import NotFoundError
from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord, Scope
from ambrosia.storage import (
    ArtifactRepository,
    BackupHooks,
    EngagementRepository,
    EvidenceRepository,
    ExecutionRepository,
    ExportManifest,
    ScopeRepository,
    Storage,
    StorageConfig,
    export_engagement_bundle,
)
from ambrosia.storage.evidence import EvidenceStore


def test_export_bundle_contains_no_secret_values(tmp_path) -> None:
    db_config = StorageConfig(db_url=f"sqlite:///{tmp_path / 'exp.db'}", workspace_root=tmp_path)
    EvidenceStore(tmp_path / "evidence")
    storage = Storage(config=db_config)

    with storage.session() as session:
        EngagementRepository(session).create(
            Engagement(id="eng-1", name="export-me", description="d")
        )
        ScopeRepository(session).create(
            Scope(id="s1", engagement_id="eng-1", include_hosts=["192.0.2.10"])
        )
        # A secret_ref is an opaque reference and may appear; raw secret
        # material in artifact value or execution input_summary must not.
        ArtifactRepository(session).add(
            Artifact(
                id="art-1",
                engagement_id="eng-1",
                type="secret.ref",
                value={"handle": "vault://secret/1"},
                source_kind="operator",
                secret_ref="vault://secret/1",
            )
        )
        ExecutionRepository(session).add(
            ExecutionRecord(
                id="ex-1",
                engagement_id="eng-1",
                action_id="net.discovery",
                input_summary={"target": "192.0.2.10"},  # no secrets
                output_artifact_ids=["art-1"],
            )
        )

    manifest = export_engagement_bundle(storage, "eng-1", tmp_path / "bundles")

    assert isinstance(manifest, ExportManifest)
    assert manifest.engagement_id == "eng-1"
    assert manifest.artifact_count == 1
    assert manifest.execution_count == 1
    assert Path(manifest.bundle_path).is_file()
    assert manifest.sha256 == hashlib.sha256(Path(manifest.bundle_path).read_bytes()).hexdigest()

    bundle = json.loads(Path(manifest.bundle_path).read_text())
    assert bundle["engagement"]["id"] == "eng-1"
    assert bundle["scope"]["id"] == "s1"
    assert bundle["artifacts"][0]["id"] == "art-1"
    assert bundle["executions"][0]["id"] == "ex-1"

    # Secret material never appears in the bundle text.
    bundle_text = Path(manifest.bundle_path).read_text()
    assert "password" not in bundle_text.lower()
    assert "token" not in bundle_text.lower()
    assert "credential" not in bundle_text.lower()

    # Opaque references are allowed.
    assert "vault://secret/1" in bundle_text


def test_export_bundle_includes_evidence_files(tmp_path) -> None:
    db_config = StorageConfig(db_url=f"sqlite:///{tmp_path / 'exp2.db'}", workspace_root=tmp_path)
    storage = Storage(config=db_config)

    source = tmp_path / "evidence.bin"
    source.write_bytes(b"evidence-content")

    with storage.session() as session:
        EngagementRepository(session).create(Engagement(id="eng-2", name="export-evidence"))
        repo = EvidenceRepository(session, store=storage.evidence)
        repo.record_file(source, engagement_id="eng-2")

    hooks = BackupHooks()
    captured = {}
    hooks.register_pre(lambda eid: captured.setdefault("pre", eid))
    hooks.register_post(lambda m: captured.setdefault("post", m.engagement_id))

    manifest = export_engagement_bundle(storage, "eng-2", tmp_path / "bundles2", hooks=hooks)
    assert captured["pre"] == "eng-2"
    assert captured["post"] == "eng-2"
    assert manifest.evidence_files == ["eng-2_evidence.zip"]
    assert (tmp_path / "bundles2" / "eng-2_evidence.zip").is_file()


def test_export_unknown_engagement_raises(tmp_path) -> None:
    storage = Storage()
    with pytest.raises(NotFoundError):
        export_engagement_bundle(storage, "does-not-exist", tmp_path / "bundles3")
