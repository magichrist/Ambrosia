"""Alembic migration tests: empty DB -> current schema, reproducibly."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from ambrosia.storage.base import Base

EXPECTED_TABLES = {
    "engagements",
    "scopes",
    "targets",
    "artifacts",
    "executions",
    "execution_events",
    "findings",
    "approval_records",
    "evidence_metadata",
}


def _repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in [path] + list(path.parents):
        if (parent / "alembic.ini").is_file():
            return parent
    raise RuntimeError("alembic.ini not found")


def _run_alembic(command_name: str, db_url: str, revision: str = "head") -> None:
    ini = _repo_root() / "alembic.ini"
    config = Config(str(ini))
    config.set_main_option("sqlalchemy.url", db_url)
    import os

    os.environ["AMBROSIA_DB_URL"] = db_url
    if command_name == "upgrade":
        command.upgrade(config, revision)
    elif command_name == "downgrade":
        command.downgrade(config, revision)


def test_alembic_upgrade_head_creates_valid_db(tmp_path) -> None:
    db_path = tmp_path / "migrated.db"
    db_url = f"sqlite:///{db_path}"
    assert not db_path.is_file()

    _run_alembic("upgrade", db_url)

    assert db_path.is_file()
    engine = create_engine(db_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names()) - {"alembic_version"}
    assert EXPECTED_TABLES <= table_names, f"missing tables: {EXPECTED_TABLES - table_names}"


def test_alembic_upgrade_head_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "idem.db"
    db_url = f"sqlite:///{db_path}"
    _run_alembic("upgrade", db_url)
    _run_alembic("upgrade", db_url)  # second run must be a no-op

    engine = create_engine(db_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names()) - {"alembic_version"}
    assert EXPECTED_TABLES <= table_names


def test_migration_is_reproducible_via_downgrade_and_upgrade(tmp_path) -> None:
    db_path = tmp_path / "repro.db"
    db_url = f"sqlite:///{db_path}"
    _run_alembic("upgrade", db_url)
    _run_alembic("downgrade", db_url, revision="base")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names()) - {"alembic_version"}
    assert table_names == set(), f"expected empty schema after downgrade: {table_names}"

    _run_alembic("upgrade", db_url)
    # Re-inspect: the previous Inspector caches table names from before the
    # upgrade re-created the schema.
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names()) - {"alembic_version"}
    assert EXPECTED_TABLES <= table_names


def test_orm_metadata_matches_migrated_schema(tmp_path) -> None:
    """The ORM metadata and the migrated schema contain the same columns."""
    db_path = tmp_path / "meta.db"
    db_url = f"sqlite:///{db_path}"
    _run_alembic("upgrade", db_url)

    engine = create_engine(db_url)
    inspector = inspect(engine)

    orm_tables = Base.metadata.tables
    assert set(orm_tables) == EXPECTED_TABLES
    for table_name, table in orm_tables.items():
        db_columns = {column["name"] for column in inspector.get_columns(table_name)}
        orm_columns = {column.name for column in table.columns}
        assert orm_columns <= db_columns, (
            f"table {table_name}: ORM columns missing in DB: {orm_columns - db_columns}"
        )
