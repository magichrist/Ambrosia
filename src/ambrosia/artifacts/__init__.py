"""Built-in artifact type definitions and lifecycle helpers.

Artifact types wrap the shared :class:`ambrosia.domain.models.Artifact` with a
type-specific value schema. Only opaque references are stored; raw secret
material is never persisted.
"""

from __future__ import annotations

from ambrosia.artifacts.lifecycle import (
    active_artifacts,
    artifacts_for_target,
    artifacts_not_bound_to_target,
    create_artifact,
    is_expired,
    match_required_artifacts,
    matches_requirement,
    superseded_ids,
)
from ambrosia.artifacts.models import (
    TYPE_REGISTRY,
    DomainArtifact,
    DomainValue,
    EvidenceRefArtifact,
    EvidenceRefValue,
    FindingArtifact,
    HostArtifact,
    HostRoleArtifact,
    HostRoleValue,
    HostValue,
    ObservationArtifact,
    SecretRefArtifact,
    SecretRefValue,
    ServiceArtifact,
    ServiceValue,
    UserRefArtifact,
    UserRefValue,
)

__all__ = [
    # lifecycle
    "create_artifact",
    "is_expired",
    "superseded_ids",
    "active_artifacts",
    "artifacts_for_target",
    "artifacts_not_bound_to_target",
    "matches_requirement",
    "match_required_artifacts",
    # models
    "HostValue",
    "ServiceValue",
    "DomainValue",
    "HostRoleValue",
    "UserRefValue",
    "SecretRefValue",
    "EvidenceRefValue",
    "HostArtifact",
    "ServiceArtifact",
    "DomainArtifact",
    "HostRoleArtifact",
    "UserRefArtifact",
    "SecretRefArtifact",
    "EvidenceRefArtifact",
    "ObservationArtifact",
    "FindingArtifact",
    "TYPE_REGISTRY",
    # ObservationArtifact / FindingArtifact imported above via models module
]
