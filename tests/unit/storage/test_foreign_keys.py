"""Foreign key enforcement tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord
from ambrosia.storage import Storage, StorageConfig
from ambrosia.storage.base import to_storage_dt
from ambrosia.storage.models import (
    ApprovalRecordORM,
    ArtifactORM,
    EngagementORM,
    ExecutionEventORM,
    ExecutionORM,
    FindingORM,
)


def _config(tmp_path, name: str) -> StorageConfig:
    return StorageConfig(db_url=f"sqlite:///{tmp_path / name}", workspace_root=tmp_path)


def _add_engagement(session, id: str = "eng-1") -> None:
    session.add(
        EngagementORM(
            id=id,
            name="e",
            status="active",
            created_at=to_storage_dt(datetime.utcnow()),
            updated_at=to_storage_dt(datetime.utcnow()),
        )
    )


def test_artifact_requires_valid_engagement(tmp_path) -> None:
    from ambrosia.storage.repositories import ArtifactRepository

    storage = Storage(config=_config(tmp_path, "fk_art.db"))
    with storage.session() as session:
        _add_engagement(session)
        session.flush()
        repo = ArtifactRepository(session)
        with pytest.raises(IntegrityError):
            repo.add(
                Artifact(
                    id="art-x",
                    engagement_id="nope",
                    type="network.host",
                    value={},
                    source_kind="operator",
                )
            )


def test_execution_requires_valid_engagement(tmp_path) -> None:
    from ambrosia.storage.repositories import ExecutionRepository

    storage = Storage(config=_config(tmp_path, "fk_ex.db"))
    with storage.session() as session:
        _add_engagement(session)
        session.flush()
        repo = ExecutionRepository(session)
        with pytest.raises(IntegrityError):
            repo.add(
                ExecutionRecord(
                    id="ex-x",
                    engagement_id="nope",
                    status="draft",
                )
            )


def test_execution_event_requires_valid_execution(tmp_path) -> None:
    from ambrosia.storage.repositories import ExecutionRepository

    storage = Storage(config=_config(tmp_path, "fk_evt.db"))
    with storage.session() as session:
        _add_engagement(session)
        session.flush()
        repo = ExecutionRepository(session)
        with pytest.raises(IntegrityError):
            repo.add_event("nope-execution", "ProgressEvent", {}, 0)


def test_approval_requires_valid_engagement(tmp_path) -> None:
    from ambrosia.storage.repositories import ApprovalRecordRepository

    storage = Storage(config=_config(tmp_path, "fk_ap.db"))
    with storage.session() as session:
        _add_engagement(session)
        session.flush()
        repo = ApprovalRecordRepository(session)
        with pytest.raises(IntegrityError):
            repo.create(engagement_id="nope", effect="remote_change")


def test_evidence_requires_valid_engagement(tmp_path) -> None:
    from ambrosia.storage.repositories import EvidenceRepository
    from ambrosia.storage.evidence import EvidenceStore

    storage = Storage(config=_config(tmp_path, "fk_ev.db"))
    store = EvidenceStore(tmp_path / "evidence")
    with storage.session() as session:
        _add_engagement(session)
        session.flush()
        repo = EvidenceRepository(session, store=store)
        with pytest.raises(IntegrityError):
            repo.record_file(__file__, engagement_id="nope")


def test_cascade_delete_engagement_removes_dependents(tmp_path) -> None:
    storage = Storage(config=_config(tmp_path, "fk_cascade.db"))
    with storage.session() as session:
        _add_engagement(session, "eng-1")
        session.flush()
        session.add(
            ArtifactORM(
                id="art-1",
                engagement_id="eng-1",
                type="network.host",
                value={},
                source_kind="operator",
                created_at=to_storage_dt(datetime.utcnow()),
            )
        )
        session.add(
            ExecutionORM(
                id="ex-1",
                engagement_id="eng-1",
                status="draft",
                created_at=to_storage_dt(datetime.utcnow()),
            )
        )
        session.flush()
        session.add(
            ExecutionEventORM(
                id="evt-1",
                execution_id="ex-1",
                kind="ProgressEvent",
                payload={},
                timestamp=to_storage_dt(datetime.utcnow()),
                sequence=0,
            )
        )
        session.add(
            FindingORM(
                id="finding-1",
                engagement_id="eng-1",
                title="t",
                severity="info",
                created_at=to_storage_dt(datetime.utcnow()),
            )
        )
        session.flush()

    storage2 = Storage(config=_config(tmp_path, "fk_cascade.db"))
    with storage2.session() as session:
        orm = session.get(EngagementORM, "eng-1")
        assert orm is not None
        session.delete(orm)
        session.flush()

    storage3 = Storage(config=_config(tmp_path, "fk_cascade.db"))
    with storage3.session() as session:
        assert session.get(EngagementORM, "eng-1") is None
        assert session.get(ArtifactORM, "art-1") is None
        assert session.get(ExecutionORM, "ex-1") is None
        assert session.get(ExecutionEventORM, "evt-1") is None
        assert session.get(FindingORM, "finding-1") is None
