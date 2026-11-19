"""Application service for engagement scopes.

The scope is the explicit authorization boundary of an engagement. Defaults are
conservative: an empty scope authorizes nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from ambrosia.application._base import _BaseService
from ambrosia.domain.errors import NotFoundError, ValidationError
from ambrosia.domain.models import Scope
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    EngagementRepository as EngagementRepositoryProtocol,
)
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    ScopeRepository as ScopeRepositoryProtocol,
)


class ScopeDTO(BaseModel):
    """Safe display representation of an engagement scope."""

    id: str
    engagement_id: str
    include_hosts: list[str]
    include_cidrs: list[str]
    include_domains: list[str]
    exclude_hosts: list[str]
    exclude_cidrs: list[str]
    allowed_ports: list[int] | None = None
    expires_at: str | None = None
    max_concurrency: int
    max_requests_per_second: float | None = None
    allowed_effects: list[str]
    require_approval_for: list[str]


class ScopeService(_BaseService):
    def show(self, engagement_id: str) -> ScopeDTO:
        with self._session() as session:
            scope_repo = cast(
                "ScopeRepositoryProtocol",  # noqa: TC001
                self._repo("scope_repo", session),
            )
            engagement_repo = cast(
                "EngagementRepositoryProtocol",  # noqa: TC001
                self._repo("engagement_repo", session),
            )
            if engagement_repo.get(engagement_id) is None:
                raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                    f"engagement {engagement_id!r} not found"
                )
            scope = scope_repo.get_for_engagement(engagement_id)
            if scope is None:
                raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                    f"no scope defined for engagement {engagement_id!r}"
                )
            return self._dto(scope)

    def update(
        self,
        engagement_id: str,
        *,
        include_hosts: list[str] | None = None,
        include_cidrs: list[str] | None = None,
        include_domains: list[str] | None = None,
        exclude_hosts: list[str] | None = None,
        exclude_cidrs: list[str] | None = None,
        allowed_ports: list[int] | None = None,
        expires_at: str | None = None,
        max_concurrency: int | None = None,
        max_requests_per_second: float | None = None,
        allowed_effects: list[str] | None = None,
        require_approval_for: list[str] | None = None,
    ) -> ScopeDTO:
        """Replace the provided scope fields (unspecified fields are unchanged).

        Raises :class:`~ambrosia.domain.errors.ValidationError` if the
        resulting scope is invalid (for example, include/exclude overlap).
        """
        with self._session() as session:
            scope_repo = cast(
                "ScopeRepositoryProtocol",  # noqa: TC001
                self._repo("scope_repo", session),
            )
            engagement_repo = cast(
                "EngagementRepositoryProtocol",  # noqa: TC001
                self._repo("engagement_repo", session),
            )
            if engagement_repo.get(engagement_id) is None:
                raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                    f"engagement {engagement_id!r} not found"
                )

            scope = scope_repo.get_for_engagement(engagement_id)
            if scope is None:
                scope = Scope(engagement_id=engagement_id)

            update_data: dict[str, object] = {}
            if include_hosts is not None:
                update_data["include_hosts"] = list(include_hosts)
            if include_cidrs is not None:
                update_data["include_cidrs"] = list(include_cidrs)
            if include_domains is not None:
                update_data["include_domains"] = list(include_domains)
            if exclude_hosts is not None:
                update_data["exclude_hosts"] = list(exclude_hosts)
            if exclude_cidrs is not None:
                update_data["exclude_cidrs"] = list(exclude_cidrs)
            if allowed_ports is not None:
                update_data["allowed_ports"] = list(allowed_ports)
            if expires_at is not None:
                update_data["expires_at"] = datetime.fromisoformat(expires_at)
            if max_concurrency is not None:
                update_data["max_concurrency"] = max_concurrency
            if max_requests_per_second is not None:
                update_data["max_requests_per_second"] = max_requests_per_second
            if allowed_effects is not None:
                update_data["allowed_effects"] = set(allowed_effects)
            if require_approval_for is not None:
                update_data["require_approval_for"] = set(require_approval_for)

            # Re-construct via the model so Pydantic re-runs validation (e.g.
            # the include/exclude overlap check), which model_copy(update=...)
            # does not repeat in this Pydantic version.
            try:
                scope = Scope(**{**scope.model_dump(), **update_data})
            except PydanticValidationError as exc:
                raise ValidationError(  # noqa: TRY003 - operator-facing message
                    str(exc)
                ) from exc
            scope_repo.update(scope)
            return self._dto(scope)

    @staticmethod
    def _dto(scope: Scope) -> ScopeDTO:
        return ScopeDTO(
            id=scope.id,
            engagement_id=scope.engagement_id,
            include_hosts=sorted(scope.include_hosts),
            include_cidrs=sorted(scope.include_cidrs),
            include_domains=sorted(scope.include_domains),
            exclude_hosts=sorted(scope.exclude_hosts),
            exclude_cidrs=sorted(scope.exclude_cidrs),
            allowed_ports=(
                sorted(scope.allowed_ports) if scope.allowed_ports is not None else None
            ),
            expires_at=scope.expires_at.isoformat() if scope.expires_at else None,
            max_concurrency=scope.max_concurrency,
            max_requests_per_second=scope.max_requests_per_second,
            allowed_effects=sorted(scope.allowed_effects),
            require_approval_for=sorted(scope.require_approval_for),
        )


__all__ = ["ScopeDTO", "ScopeService"]
