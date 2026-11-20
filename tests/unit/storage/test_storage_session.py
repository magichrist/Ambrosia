"""Database engine, session, and configuration tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ambrosia.domain.models import Engagement
from ambrosia.storage import (
    Storage,
    StorageConfig,
    create_engine_from_config,
    session_scope,
)
from ambrosia.storage.base import to_storage_dt
from ambrosia.storage.models import ArtifactORM, EngagementORM
from ambrosia.storage.repositories import EngagementRepository


def test_in_memory_storage_creates_tables() -> None:
    storage = Storage()  # default: in-memory SQLite
    with storage.session() as session:
        engagement = repo_create(session, id="eng-inmem")
        assert session.get(EngagementORM, engagement.id) is not None


def test_workspace_local_db_path_persists_across_instances(tmp_path: Path) -> None:
    config = StorageConfig(db_url="sqlite:///workspace.db", workspace_root=tmp_path)
    storage = Storage(config=config)
    assert (tmp_path / "workspace.db").is_file()
    with storage.session() as session:
        engagement = repo_create(session, id="eng-persist", name="alpha")

    # A new handle to the same workspace DB sees the same data.
    storage2 = Storage(config=config)
    with storage2.session() as session:
        found = session.get(EngagementORM, engagement.id)
        assert found is not None
        assert found.name == "alpha"


def test_workspace_local_db_relative_path_resolved_against_workspace_root(
    tmp_path: Path,
) -> None:
    config = StorageConfig(db_url="sqlite:///nested/ambrosia.db", workspace_root=tmp_path)
    engine = create_engine_from_config(config)
    assert Path(engine.url.database).is_absolute()
    storage = Storage(config=config)
    assert (tmp_path / "nested" / "ambrosia.db").is_file()
    storage.engine.dispose()


def test_foreign_keys_are_enforced_by_default(tmp_path: Path) -> None:
    config = StorageConfig(db_url=f"sqlite:///{tmp_path / 'fk.db'}", workspace_root=tmp_path)
    storage = Storage(config=config)
    with storage.session() as session:
        session.add(EngagementORM(id="eng-1", name="e", status="active"))
        session.flush()
        bad = ArtifactORM(
            id="art-1",
            engagement_id="does-not-exist",
            type="network.host",
            value={},
            source_kind="operator",
            created_at=to_storage_dt(datetime.utcnow()),
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            session.flush()


def test_timestamps_are_stored_in_utc() -> None:
    storage = Storage()
    naive = datetime(2026, 1, 1, 12, 0, 0)
    with storage.session() as session:
        engagement = repo_create(session, id="eng-utc", created_at=naive)
        row = session.get(EngagementORM, engagement.id)
    # SQLite has no native time-zone-aware timestamp, so the stored value is
    # naive and interpreted as UTC at the converter boundary.
    assert row.created_at.tzinfo is None
    assert row.created_at == naive
    # Round trip through the converter boundary preserves the instant.
    from ambrosia.storage.converters import engagement_from_orm

    back = engagement_from_orm(row)
    assert back.created_at == naive


def test_session_scope_rolls_back_on_exception(tmp_path: Path) -> None:
    config = StorageConfig(db_url=f"sqlite:///{tmp_path / 'tx.db'}", workspace_root=tmp_path)
    storage = Storage(config=config)
    with storage.session() as session:
        EngagementRepository(session).create(Engagement(id="kept-id", name="kept", description="d"))
    with storage.session() as session:
        try:
            with session_scope(session):
                EngagementRepository(session).create(
                    Engagement(id="tx-id", name="tx", description="d")
                )
                EngagementRepository(session).create(
                    Engagement(id="tx-id", name="tx-dup", description="d")
                )
        except IntegrityError:
            pass
    with storage.session() as session:
        names = {row.name for row in session.execute(select(EngagementORM)).scalars().all()}
        assert names == {"kept"}


def repo_create(session, id: str, name: str = "e", created_at: datetime | None = None):
    engagement = Engagement(
        id=id,
        name=name,
        description="d",
        status="active",
        created_at=created_at or datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    return EngagementRepository(session).create(engagement)
