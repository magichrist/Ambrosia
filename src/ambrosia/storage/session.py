"""Database engine, session factory, and storage configuration.

Supports workspace-local file SQLite databases and an in-memory SQLite option
for tests. SQLite foreign keys are enforced on every connection (they are off
by default in SQLite).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, event
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.orm import Session, sessionmaker

from ambrosia.storage.base import Base

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine


def enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """Enforce FOREIGN KEY constraints on every SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class StorageConfig:
    """Configuration for a :class:`Storage` instance.

    ``db_url`` is a SQLAlchemy database URL. Relative file paths (e.g.
    ``sqlite:///workspace.db``) are resolved against ``workspace_root`` so a
    workspace keeps its database local to itself. ``sqlite:///:memory:`` with
    a shared static pool is the in-memory option used by tests.
    """

    def __init__(
        self,
        *,
        db_url: str = "sqlite:///:memory:",
        workspace_root: str | os.PathLike[str] | None = None,
        evidence_dir: str | os.PathLike[str] | None = None,
        echo: bool = False,
    ) -> None:
        self.db_url = db_url
        self.workspace_root = Path(workspace_root) if workspace_root is not None else None
        self.evidence_dir = Path(evidence_dir) if evidence_dir is not None else None
        self.echo = echo


def _resolve_db_url(db_url: str, workspace_root: Path | None) -> str:
    if not db_url.startswith("sqlite:///"):
        return db_url
    if ":memory:" in db_url:
        return db_url
    prefix = "sqlite:///"
    relative_path = db_url[len(prefix) :]
    if Path(relative_path).is_absolute():
        return db_url
    if workspace_root is not None:
        return prefix + str((workspace_root / relative_path).resolve())
    return prefix + str(Path(relative_path).resolve())


def create_engine_from_config(config: StorageConfig) -> Engine:
    """Create a SQLAlchemy engine from a :class:`StorageConfig`."""
    db_url = _resolve_db_url(config.db_url, config.workspace_root)
    connect_args: dict[str, Any] = (
        {"check_same_thread": False} if db_url.startswith("sqlite:") else {}
    )
    if ":memory:" in db_url:
        # StaticPool shares a single connection (and hence one in-memory
        # database) across all sessions created from this engine.
        from sqlalchemy.pool import StaticPool

        return create_engine(
            db_url, connect_args=connect_args, poolclass=StaticPool, echo=config.echo
        )
    return create_engine(db_url, connect_args=connect_args, echo=config.echo)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables defined by the ORM metadata.

    Tests and standalone setups use this. Alembic-managed deployments should
    construct :class:`Storage` with ``create_tables=False`` and run migrations
    instead.
    """
    Base.metadata.create_all(engine)


def drop_all(engine: Engine) -> None:
    Base.metadata.drop_all(engine)


@contextmanager
def session_scope(session: Session) -> Iterator[Session]:
    """Transactional scope around a series of operations.

    Commits on success; rolls back and re-raises on exception. If an operation
    inside the block fails and the caller handles that exception, the
    transaction is already rolled back: the exit path swallows
    ``PendingRollbackError`` from commit instead of masking the original
    outcome.
    """
    try:
        yield session
        try:
            session.commit()
        except PendingRollbackError:
            # The transaction was already rolled back after an in-block
            # failure that the caller handled; nothing remains to commit.
            pass
    except Exception:
        if session.in_transaction():
            session.rollback()
        raise


class Storage:
    """Handle to a configured storage instance.

    Holds the engine, session factory, and evidence store. Repositories are
    constructed with an individual session from :meth:`session`.
    """

    def __init__(
        self,
        config: StorageConfig | None = None,
        *,
        create_tables: bool = True,
    ) -> None:
        self.config = config or StorageConfig()
        self.engine = create_engine_from_config(self.config)
        self.session_factory = create_session_factory(self.engine)
        # A file-based SQLite database needs its parent directory to exist
        # before tables can be created, e.g. a workspace-local DB under a
        # nested path. In-memory databases skip this.
        database = self.engine.url.database
        if database and str(self.engine.url).startswith("sqlite:"):
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        if create_tables:
            init_db(self.engine)
        evidence_dir = self.config.evidence_dir
        if evidence_dir is None:
            if self.config.workspace_root is not None:
                evidence_dir = self.config.workspace_root / ".ambrosia" / "evidence"
            else:
                evidence_dir = Path.home() / ".ambrosia" / "evidence"
        from ambrosia.storage.evidence import EvidenceStore

        self.evidence = EvidenceStore(evidence_dir)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a transactional session (commit/rollback handled automatically)."""
        session = self.session_factory()
        try:
            with session_scope(session) as session:
                yield session
        finally:
            session.close()

    def create_all(self) -> None:
        init_db(self.engine)
