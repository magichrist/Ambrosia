"""Explicit, per-run authorization gate for high-impact operations.

Read-only actions are governed by the normal scope/effect policy. Actions that
access credentials, change remote state, or perform authentication are subject
to an additional gate: the operator must supply a non-empty authorization
reference for that run. The reference is recorded on the decision so the run
is attributable.

This module is deliberately small and dependency-free so it can be called from
application services, UI adapters, and action handlers alike. It is a
confirmation gate, not a cryptographic control — it ensures a high-impact run
was explicitly authorized rather than triggered accidentally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ambrosia.domain.errors import PolicyBlockedError

if TYPE_CHECKING:
    from ambrosia.domain.action import ActionDefinition
    from ambrosia.domain.protocols import ActionRequest

# Effects that require an explicit authorization reference in addition to the
# normal scope effect allowlist and the engine's approval state transition.
HIGH_IMPACT_EFFECTS: frozenset[str] = frozenset(
    {"credential_access", "remote_change", "authentication"}
)

# Reserved action input key used to carry the reference into a handler. It is
# never part of a tool argv and is removed before argv construction.
AUTHORIZATION_INPUT = "authorization_reference"


@dataclass(frozen=True)
class Authorization:
    """An operator's explicit authorization for one high-impact execution."""

    reference: str
    decided_by: str = "operator"

    def __post_init__(self) -> None:
        reference = self.reference.strip()
        decided_by = self.decided_by.strip() or "operator"
        if not reference:
            raise PolicyBlockedError(  # noqa: TRY003 - operator-facing message
                "an authorization reference is required for this operation"
            )
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "decided_by", decided_by)

    def as_details(self) -> dict[str, str]:
        return {"authorization_reference": self.reference, "decided_by": self.decided_by}


def is_high_impact(definition: ActionDefinition) -> bool:
    """True when ``definition`` needs the extra authorization gate."""
    return bool(HIGH_IMPACT_EFFECTS.intersection(definition.effects)) or bool(
        definition.approval_required
    )


class AuthorizationService:
    """Stateless gate that requires an authorization for high-impact actions."""

    def require(
        self,
        definition: ActionDefinition,
        authorization: Authorization | None,
    ) -> Authorization | None:
        """Return the authorization, or raise :class:`PolicyBlockedError`.

        Non-high-impact actions pass through untouched. High-impact actions
        require a valid, non-empty :class:`Authorization`.
        """
        if not is_high_impact(definition):
            return None
        if authorization is None:
            raise PolicyBlockedError(  # noqa: TRY003 - operator-facing message
                f"action {definition.id!r} requires an explicit authorization reference; "
                "supply --authorization (CLI) or the authorization field (TUI)",
                details={"action_id": definition.id, "effects": list(definition.effects)},
            )
        return authorization

    def require_reference(
        self,
        definition: ActionDefinition,
        reference: str | None,
        *,
        decided_by: str = "operator",
    ) -> Authorization | None:
        """Convenience wrapper: build an :class:`Authorization` from a string."""
        authorization = (
            Authorization(reference=reference, decided_by=decided_by) if reference else None
        )
        return self.require(definition, authorization)


def require_request_authorization(
    request: ActionRequest,
    definition: ActionDefinition,
) -> Authorization:
    """Handler-level gate: read the reserved input and require authorization.

    Called by high-impact handlers before any argv is built or any process is
    started. The reserved key is not forwarded to the tool.
    """
    raw = request.inputs.get(AUTHORIZATION_INPUT)
    if not isinstance(raw, str) or not raw.strip():
        raise PolicyBlockedError(  # noqa: TRY003 - operator-facing message
            f"action {definition.id!r} requires an explicit authorization reference "
            f"in inputs[{AUTHORIZATION_INPUT!r}]",
            details={"action_id": definition.id},
        )
    return Authorization(reference=raw)


__all__ = [
    "AUTHORIZATION_INPUT",
    "HIGH_IMPACT_EFFECTS",
    "Authorization",
    "AuthorizationService",
    "is_high_impact",
    "require_request_authorization",
]
