"""Application service for engagements.

Engagements are the top-level unit of work. Creating an engagement also
creates an empty (conservative) scope for it, so scope/target commands work
immediately after ``engagement create``.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from ambrosia.application._base import _BaseService
from ambrosia.domain.errors import NotFoundError
from ambrosia.domain.models import Engagement, Scope
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    EngagementRepository as EngagementRepositoryProtocol,
)
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    ScopeRepository as ScopeRepositoryProtocol,
)


class EngagementDTO(BaseModel):
    """Safe display representation of an engagement (no secrets)."""

    id: str
    name: str
    description: str | None = None
    status: str
    created_at: str
    updated_at: str
    scope_id: str | None = None


class EngagementListDTO(BaseModel):
    engagements: list[EngagementDTO]


class EngagementService(_BaseService):
    def create(self, name: str, description: str | None = None) -> EngagementDTO:
        """Create an engagement with an empty conservative scope."""
        with self._session() as session:
            engagement_repo = cast(
                "EngagementRepositoryProtocol",  # noqa: TC001
                self._repo("engagement_repo", session),
            )
            scope_repo = cast(
                "ScopeRepositoryProtocol",  # noqa: TC001
                self._repo("scope_repo", session),
            )

            engagement = Engagement(name=name, description=description)
            engagement = engagement_repo.create(engagement)

            scope = Scope(engagement_id=engagement.id)
            scope = scope_repo.create(scope)

            engagement.scope_id = scope.id
            engagement_repo.update(engagement)
            return self._dto(engagement)

    def list(self) -> EngagementListDTO:
        with self._session() as session:
            engagement_repo = cast(
                "EngagementRepositoryProtocol",  # noqa: TC001
                self._repo("engagement_repo", session),
            )
            return EngagementListDTO(engagements=[self._dto(e) for e in engagement_repo.list()])

    def get(self, engagement_id: str) -> EngagementDTO:
        with self._session() as session:
            engagement_repo = cast(
                "EngagementRepositoryProtocol",  # noqa: TC001
                self._repo("engagement_repo", session),
            )
            engagement = engagement_repo.get(engagement_id)
            if engagement is None:
                raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                    f"engagement {engagement_id!r} not found"
                )
            return self._dto(engagement)

    def open(self, engagement_id: str) -> EngagementDTO:
        """Alias of ``get``: open/use an engagement (returns it for the caller)."""
        return self.get(engagement_id)

    @staticmethod
    def _dto(engagement: Engagement) -> EngagementDTO:
        return EngagementDTO(
            id=engagement.id,
            name=engagement.name,
            description=engagement.description,
            status=engagement.status,
            created_at=engagement.created_at.isoformat(),
            updated_at=engagement.updated_at.isoformat(),
            scope_id=engagement.scope_id,
        )


__all__ = ["EngagementDTO", "EngagementListDTO", "EngagementService"]
