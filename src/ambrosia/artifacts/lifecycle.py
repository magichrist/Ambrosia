"""Artifact creation, provenance, supersession, expiry, and scoping.

Pure helpers operate on :class:`ambrosia.domain.models.Artifact` instances and
never touch storage. The factory builds type-specific artifacts with full
provenance and rejects raw secret material.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ambrosia.artifacts.models import TYPE_REGISTRY
from ambrosia.domain.models import Artifact, _utc_now

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from ambrosia.domain.action import ArtifactRequirement


def create_artifact(
    *,
    engagement_id: str,
    type: str,
    value: dict[str, object],
    source_kind: Literal["action", "preset", "operator", "import"] = "operator",
    source_id: str | None = None,
    source_execution_id: str | None = None,
    target_ref: str | None = None,
    confidence: float | None = None,
    sensitivity: Literal["public", "internal", "sensitive", "secret"] = "internal",
    secret_ref: str | None = None,
    scope_binding: dict[str, object] | None = None,
    supersedes: str | None = None,
    expires_at: datetime | None = None,
    metadata: dict[str, object] | None = None,
) -> Artifact:
    """Create and validate a type-specific artifact.

    The ``value`` payload is validated against the registered type schema.
    Provenance (source, target binding), sensitivity labels, optional secret
    reference, supersession link, and expiry are all stored on the artifact.
    Raw secret material in ``value`` is rejected by the base ``Artifact``
    model; only ``secret_ref`` (an opaque handle) may be used for secrets.

    Expiry is not rejected at creation time: an artifact may be imported or
    backfilled with an expiry already in the past. Expired artifacts are
    filtered out at read time by :func:`is_expired` and :func:`active_artifacts`.
    """
    artifact_cls = TYPE_REGISTRY.get(type)
    if artifact_cls is None:
        # Custom (non-built-in) type: store as a plain Artifact with a dict value.
        return Artifact(
            engagement_id=engagement_id,
            type=type,
            value=dict(value),
            source_kind=source_kind,
            source_id=source_id,
            source_execution_id=source_execution_id,
            target_ref=target_ref,
            confidence=confidence,
            sensitivity=sensitivity,
            secret_ref=secret_ref,
            scope_binding=scope_binding,
            supersedes=supersedes,
            expires_at=expires_at,
            metadata=metadata or {},
        )

    artifact = artifact_cls(  # type: ignore[call-arg]  # subclass defaults `type` to its registered literal
        engagement_id=engagement_id,
        value=value,
        source_kind=source_kind,
        source_id=source_id,
        source_execution_id=source_execution_id,
        target_ref=target_ref,
        confidence=confidence,
        sensitivity=sensitivity,
        secret_ref=secret_ref,
        scope_binding=scope_binding,
        supersedes=supersedes,
        expires_at=expires_at,
        metadata=metadata or {},
    )
    return artifact


def is_expired(artifact: Artifact, now: datetime | None = None) -> bool:
    """Return True if the artifact's expiry has passed."""
    if artifact.expires_at is None:
        return False
    now = now or _utc_now()
    return artifact.expires_at <= now


def supersedes(artifact: Artifact) -> str | None:
    """Return the id of the artifact this artifact replaces (if any)."""
    return artifact.supersedes


def superseded_ids(artifacts: Iterable[Artifact]) -> set[str]:
    """Return ids of artifacts that are superseded by another artifact in the set."""
    superseded: set[str] = set()
    for artifact in artifacts:
        if artifact.supersedes is not None:
            superseded.add(artifact.supersedes)
    return superseded


def active_artifacts(
    artifacts: Iterable[Artifact], now: datetime | None = None
) -> list[Artifact]:
    """Return artifacts that are neither expired nor superseded."""
    now = now or _utc_now()
    superseded = superseded_ids(artifacts)
    return [
        a
        for a in artifacts
        if a.id not in superseded and not is_expired(a, now=now)
    ]


def artifacts_for_target(
    artifacts: Iterable[Artifact], target_ref: str
) -> list[Artifact]:
    """Return artifacts bound to the given target."""
    return [a for a in artifacts if a.target_ref == target_ref]


def artifacts_not_bound_to_target(
    artifacts: Iterable[Artifact],
) -> list[Artifact]:
    """Return artifacts with no target binding (global/scope-level artifacts)."""
    return [a for a in artifacts if a.target_ref is None]


def matches_requirement(
    artifact: Artifact,
    requirement: ArtifactRequirement,
    action_target_ref: str | None,
) -> bool:
    """Return True if an artifact can satisfy an action requirement.

    When ``requirement.same_target`` is true (the default), the artifact must
    be bound to the same target as the action. This prevents artifacts from one
    host from silently satisfying requirements for another host. Cross-target
    use is only allowed when the action explicitly declares it
    (``same_target=False``).
    """
    if requirement.same_target and action_target_ref is not None:
        if artifact.target_ref != action_target_ref:
            return False
    return True


def match_required_artifacts(
    artifacts: Iterable[Artifact],
    requirements: Iterable[ArtifactRequirement],
    action_target_ref: str | None = None,
) -> tuple[list[str], list[str]]:
    """Match artifact ids against action requirements.

    Returns ``(matched_ids, missing_types)``. Respects per-requirement
    ``same_target`` semantics so cross-host artifacts are never matched
    unless the action explicitly allows it.
    """
    artifact_list = list(artifacts)
    matched_ids: list[str] = []
    missing_types: list[str] = []
    for requirement in requirements:
        candidates = [
            a
            for a in artifact_list
            if a.type == requirement.type
            and matches_requirement(a, requirement, action_target_ref)
        ]
        if candidates:
            matched_ids.extend(a.id for a in candidates)
        else:
            missing_types.append(requirement.type)
    return matched_ids, missing_types
