"""Effect classification for actions.

Classifies declared action effects against a scope's allowed-effects and
approval-required sets. Unknown effects are never silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Effect classes named in the shared contracts (docs/00_MASTER_PLAN.md 10.2).
# Effects outside this set are unknown and blocked by default.
KNOWN_EFFECTS: Final[frozenset[str]] = frozenset(
    {
        "local_read",
        "local_write",
        "local_script",
        "network_observe",
        "remote_read",
        "authentication",
        "remote_change",
        "credential_access",
        "unknown",
    }
)


@dataclass(frozen=True)
class EffectClassification:
    """Result of classifying an action's declared effects against policy."""

    effects: tuple[str, ...]
    allowed: tuple[str, ...]
    blocked: tuple[str, ...]
    requires_approval: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def is_fully_allowed(self) -> bool:
        """True when no effect is blocked and none requires approval."""
        return not self.blocked and not self.requires_approval

    @property
    def has_unknown(self) -> bool:
        return bool(self.unknown)


class EffectClassifier:
    """Classifies action effects against policy settings."""

    def classify(
        self,
        effects: list[str],
        *,
        allowed_effects: frozenset[str],
        require_approval_for: frozenset[str],
    ) -> EffectClassification:
        """Classify ``effects`` against the scope's allowed/approval sets.

        Unknown effects are blocked. Effects not in ``allowed_effects`` are
        blocked. Effects in ``require_approval_for`` require approval.
        """
        allowed: list[str] = []
        blocked: list[str] = []
        requires_approval: list[str] = []
        unknown: list[str] = []

        for effect in effects:
            if effect not in KNOWN_EFFECTS:
                unknown.append(effect)
                blocked.append(effect)  # unknown effects are never silently accepted
            elif effect not in allowed_effects:
                blocked.append(effect)
            elif effect in require_approval_for:
                requires_approval.append(effect)
            else:
                allowed.append(effect)

        return EffectClassification(
            effects=tuple(effects),
            allowed=tuple(allowed),
            blocked=tuple(blocked),
            requires_approval=tuple(requires_approval),
            unknown=tuple(unknown),
        )


__all__ = ["EffectClassifier", "EffectClassification", "KNOWN_EFFECTS"]
