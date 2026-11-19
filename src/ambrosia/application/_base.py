"""Shared base for application services.

Services receive repository instances (typically fakes in tests) or, in
production, a :class:`ambrosia.storage.Storage` instance from which concrete
repositories are built per method call inside a transactional session.
All repository access goes through the shared protocols; no SQLAlchemy queries
leak into the application or CLI layers.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import ContextManager, Iterator, cast

from sqlalchemy.orm import Session

from ambrosia.domain.protocols import (
    ArtifactRepository as ArtifactRepositoryProtocol,
    ExecutionRepository as ExecutionRepositoryProtocol,
    EngagementRepository as EngagementRepositoryProtocol,
    ScopeRepository as ScopeRepositoryProtocol,
)
from ambrosia.storage.repositories import (
    ArtifactRepository,
    ApprovalRecordRepository,
    EngagementRepository,
    EvidenceRepository,
    ExecutionRepository,
    FindingRepository,
    ScopeRepository,
    TargetRepository as StorageTargetRepository,
)

_REPO_CLASSES: dict[str, type] = {
    "engagement_repo": EngagementRepository,
    "scope_repo": ScopeRepository,
    "artifact_repo": ArtifactRepository,
    "execution_repo": ExecutionRepository,
    "target_repo": StorageTargetRepository,
    "finding_repo": FindingRepository,
    "approval_repo": ApprovalRecordRepository,
    "evidence_repo": EvidenceRepository,
}


class _BaseService:
    def __init__(
        self,
        *,
        session_scope: ContextManager[object | None] = nullcontext,
        engagement_repo: object = None,
        scope_repo: object = None,
        artifact_repo: object = None,
        execution_repo: object = None,
        target_repo: object = None,
        finding_repo: object = None,
        approval_repo: object = None,
        evidence_repo: object = None,
    ) -> None:
        self._session_scope = session_scope
        self._repos: dict[str, object] = {
            "engagement_repo": engagement_repo,
            "scope_repo": scope_repo,
            "artifact_repo": artifact_repo,
            "execution_repo": execution_repo,
            "target_repo": target_repo,
            "finding_repo": finding_repo,
            "approval_repo": approval_repo,
            "evidence_repo": evidence_repo,
        }

    @contextmanager
    def _session(self) -> Iterator[object | None]:
        with self._session_scope() as session:
            yield session

    def _repo(self, name: str, session: object | None) -> object:
        repo = self._repos.get(name)
        if repo is not None:
            return repo
        assert session is not None, f"{name} requires a storage session"
        return _REPO_CLASSES[name](cast(Session, session))


__all__ = ["_BaseService"]
