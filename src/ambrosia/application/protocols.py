"""Protocols used by the application service layer.

The application layer depends on protocols, not on concrete storage or engine
implementations. Production implementations live in ``ambrosia.storage`` and
``ambrosia.engine``; tests use fakes.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Protocol, runtime_checkable

from ambrosia.domain.models import ExecutionRecord, Target
from ambrosia.domain.protocols import ExecutionRepository

__all__ = [
    "TargetRepository",
    "UnitOfWork",
    "PresetEngine",
    "ExecutionRepository",
]


@runtime_checkable
class TargetRepository(Protocol):
    """Read/write access to engagement targets.

    Storage-specific target records are converted to :class:`Target` domain
    models at the application boundary; the CLI never sees ORM instances.
    """

    def get(self, target_id: str) -> Target | None: ...  # pragma: no cover
    def create(  # pragma: no cover
        self,
        *,
        engagement_id: str,
        address: str,
        target_type: str = "host",
        hostname: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
    ) -> Target: ...
    def list_for_engagement(self, engagement_id: str) -> list[Target]: ...  # pragma: no cover


@runtime_checkable
class UnitOfWork(Protocol):
    """Transactional boundary for multi-repository operations.

    ``ambrosia.storage.Storage.session`` satisfies this protocol.
    """

    @contextmanager
    def session_scope(self) -> Iterator[None]: ...  # pragma: no cover


class PresetEngine(Protocol):
    """Optional execution engine for preset runs.

    Agent 5 owns ``ambrosia.engine``. When it is integrated, an engine
    satisfying this protocol can be injected into :class:`PresetService`. Until
    then, ``preset run`` degrades gracefully with a typed missing-dependency
    error instead of silently succeeding or crashing.
    """

    async def run(  # pragma: no cover - interface stub
        self,
        *,
        preset_id: str,
        execution_id: str,
        inputs: dict[str, object],
    ) -> ExecutionRecord: ...
