"""Evidence store: generated IDs, content hash, and metadata round trip."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ambrosia.domain.models import Engagement, ExecutionRecord
from ambrosia.storage import (
    EngagementRepository,
    EvidenceRepository,
    ExecutionRepository,
    Storage,
    StorageConfig,
)
from ambrosia.storage.evidence import EvidenceStore


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_evidence_metadata_content_hash_round_trip(tmp_path) -> None:
    db_config = StorageConfig(
        db_url=f"sqlite:///{tmp_path / 'ev.db'}", workspace_root=tmp_path
    )
    store = EvidenceStore(tmp_path / "evidence")
    storage = Storage(config=db_config)

    with storage.session() as session:
        EngagementRepository(session).create(Engagement(id="eng-1", name="lab"))
        ExecutionRepository(session).add(
            ExecutionRecord(id="ex-1", engagement_id="eng-1", status="draft")
        )

    source = tmp_path / "source.bin"
    source.write_bytes(b"ambrosia-evidence-fixture-bytes")

    with storage.session() as session:
        repo = EvidenceRepository(session, store=store)
        record = repo.record_file(
            source,
            engagement_id="eng-1",
            execution_id="ex-1",
            media_type="application/octet-stream",
        )

    # The file lives under a generated ID in the controlled directory.
    stored_path = store.path_for(record.relative_path)
    assert stored_path.is_file()
    assert str(stored_path).startswith(str(store.root_dir))
    assert record.relative_path == f"{record.generated_id[:2]}/{record.generated_id}"
    assert record.filename == "source.bin"
    assert record.content_hash == _sha256(source)
    assert record.size == len(source.read_bytes())
    assert record.media_type == "application/octet-stream"
    assert record.engagement_id == "eng-1"
    assert record.execution_id == "ex-1"

    # Content hash verifies against the stored file.
    assert store.verify(record.relative_path, record.content_hash)
    assert not store.verify(record.relative_path, "0" * 64)

    # Metadata is readable back from the database.
    with storage.session() as session:
        repo = EvidenceRepository(session, store=store)
        fetched = repo.get(record.id)
        assert fetched is not None
        assert fetched.generated_id == record.generated_id
        assert fetched.relative_path == record.relative_path
        assert fetched.content_hash == record.content_hash
        by_id = repo.list_by_generated_id(record.generated_id)
        assert by_id is not None
        assert by_id.content_hash == record.content_hash
        all_for_engagement = repo.list_for_engagement("eng-1")
        assert len(all_for_engagement) == 1


def test_evidence_generated_ids_are_unique(tmp_path) -> None:
    db_config = StorageConfig(
        db_url=f"sqlite:///{tmp_path / 'ev2.db'}", workspace_root=tmp_path
    )
    store = EvidenceStore(tmp_path / "evidence2")
    storage = Storage(config=db_config)

    with storage.session() as session:
        EngagementRepository(session).create(Engagement(id="eng-1", name="lab"))

    source = tmp_path / "source.bin"
    source.write_bytes(b"duplicate-content")
    ids = set()
    with storage.session() as session:
        repo = EvidenceRepository(session, store=store)
        for _ in range(5):
            record = repo.record_file(source, engagement_id="eng-1")
            ids.add(record.generated_id)
    assert len(ids) == 5
