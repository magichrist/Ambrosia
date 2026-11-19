"""Application service for targets.

Targets are engagement-authorized assets. Scope enforcement happens at
execution time (see the policy gateway), not when a target is recorded.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal, cast

from pydantic import BaseModel

from ambrosia.domain.errors import NotFoundError, ValidationError
from ambrosia.domain.models import Target
from ambrosia.domain.protocols import (
    EngagementRepository as EngagementRepositoryProtocol,
)
from ambrosia.application._base import _BaseService
from ambrosia.application.protocols import TargetRepository as TargetRepositoryProtocol

_HOSTNAME_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))*$"
)
_DOMAIN_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))+\.?$"
)


class TargetDTO(BaseModel):
    """Safe display representation of a target."""

    id: str
    engagement_id: str
    address: str
    kind: str  # host | ip | domain
    target_type: str | None = None
    hostname: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: str


class TargetListDTO(BaseModel):
    targets: list[TargetDTO]


class TargetService(_BaseService):
    def add(
        self,
        engagement_id: str,
        address: str,
        *,
        kind: str = "auto",
        hostname: str | None = None,
        notes: str | None = None,
    ) -> TargetDTO:
        """Add a target to an engagement.

        ``kind=auto`` detects IP addresses and domains; anything else is a
        plain host. The address is validated against the detected kind.
        """
        with self._session() as session:
            target_repo = cast(
                TargetRepositoryProtocol, self._repo("target_repo", session)
            )
            engagement_repo = cast(
                EngagementRepositoryProtocol, self._repo("engagement_repo", session)
            )
            if engagement_repo.get(engagement_id) is None:
                raise NotFoundError(f"engagement {engagement_id!r} not found")

            resolved_kind = self._resolve_kind(address) if kind == "auto" else kind
            # Validate the address against its kind via the domain model.
            Target(
                engagement_id=engagement_id,
                address=address,
                kind=cast(Literal["host", "ip", "domain"], resolved_kind),
            )

            record = target_repo.create(
                engagement_id=engagement_id,
                address=address.strip(),
                target_type=resolved_kind,
                hostname=hostname,
                notes=notes,
            )
            return self._dto(record)

    def list(self, engagement_id: str) -> TargetListDTO:
        with self._session() as session:
            target_repo = cast(
                TargetRepositoryProtocol, self._repo("target_repo", session)
            )
            engagement_repo = cast(
                EngagementRepositoryProtocol, self._repo("engagement_repo", session)
            )
            if engagement_repo.get(engagement_id) is None:
                raise NotFoundError(f"engagement {engagement_id!r} not found")
            return TargetListDTO(
                targets=[
                    self._dto(t)
                    for t in target_repo.list_for_engagement(engagement_id)
                ]
            )

    @staticmethod
    def _resolve_kind(address: str) -> Literal["host", "ip", "domain"]:
        address = address.strip()
        try:
            ipaddress.ip_address(address)
            return "ip"
        except ValueError:
            pass
        if _DOMAIN_RE.fullmatch(address):
            return "domain"
        if _HOSTNAME_RE.fullmatch(address):
            return "host"
        raise ValidationError(
            f"target address is not a valid host, IP, or domain: {address!r}"
        )

    @staticmethod
    def _dto(obj: object) -> TargetDTO:
        return TargetDTO(
            id=getattr(obj, "id"),
            engagement_id=getattr(obj, "engagement_id"),
            address=getattr(obj, "address"),
            kind=cast(
                str, getattr(obj, "kind", None) or getattr(obj, "target_type", "host")
            ),
            target_type=getattr(obj, "target_type", None),
            hostname=getattr(obj, "hostname", None),
            notes=getattr(obj, "notes", None),
            is_active=bool(getattr(obj, "is_active", True)),
            created_at=getattr(obj, "created_at").isoformat(),
        )


__all__ = ["TargetDTO", "TargetListDTO", "TargetService"]
