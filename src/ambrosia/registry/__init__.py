"""Action registry public interface.

Provides action definition loading, registry operations, pack management, and
the pure availability matcher. Re-exports the domain action contracts for
convenience.
"""

from __future__ import annotations

from ambrosia.domain.action import (
    ActionAvailability,
    ActionDefinition,
    ArtifactRequirement,
    ExecutorReference,
    ToolDependency,
)
from ambrosia.registry.errors import (
    ActionNotFoundError,
    DuplicateActionError,
    DuplicatePackError,
    HandlerNotFoundError,
    ManifestValidationError,
    PackConflictError,
    PackNotFoundError,
    RegistryError,
)
from ambrosia.registry.loader import (
    load_definition_from_file,
    load_definition_from_mapping,
    load_pack_from_file,
    load_pack_from_mapping,
)
from ambrosia.registry.matcher import AvailabilityMatcher
from ambrosia.registry.models import (
    ContextSnapshot,
    LoadedAction,
    LoadResult,
    PackManifest,
    PackMetadata,
    PolicySnapshot,
)
from ambrosia.registry.registry import PackEntry, Registry
from ambrosia.registry.validation import (
    ValidationResult,
    check_duplicate_ids,
    validate_action_definition,
    validate_action_id,
    validate_artifact_requirement,
    validate_dependency,
    validate_effects,
    validate_executor_reference,
    validate_version,
)

__all__ = [
    # domain contracts (re-exported)
    "ActionAvailability",
    "ActionDefinition",
    "ArtifactRequirement",
    "ExecutorReference",
    "ToolDependency",
    # errors
    "RegistryError",
    "DuplicateActionError",
    "DuplicatePackError",
    "PackNotFoundError",
    "ActionNotFoundError",
    "PackConflictError",
    "ManifestValidationError",
    "HandlerNotFoundError",
    # loading
    "load_definition_from_file",
    "load_definition_from_mapping",
    "load_pack_from_file",
    "load_pack_from_mapping",
    # registry
    "Registry",
    "PackEntry",
    # matcher
    "AvailabilityMatcher",
    # models
    "PackManifest",
    "PackMetadata",
    "LoadedAction",
    "LoadResult",
    "ContextSnapshot",
    "PolicySnapshot",
    # validation
    "ValidationResult",
    "check_duplicate_ids",
    "validate_action_definition",
    "validate_action_id",
    "validate_artifact_requirement",
    "validate_dependency",
    "validate_effects",
    "validate_executor_reference",
    "validate_version",
]
