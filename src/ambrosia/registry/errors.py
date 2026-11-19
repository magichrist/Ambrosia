"""Registry-specific errors.

All errors carry a stable ``code`` and safe, non-secret details.
"""

from __future__ import annotations

from ambrosia.domain.errors import AmbrosiaError


class RegistryError(AmbrosiaError):
    """Base error for registry operations."""

    code = "registry_error"
    message = "Registry operation failed."


class DuplicateActionError(RegistryError):
    """An action ID is already registered from a different pack."""

    code = "duplicate_action"
    message = "Action ID is already registered."


class DuplicatePackError(RegistryError):
    """A pack ID is already loaded."""

    code = "duplicate_pack"
    message = "Pack ID is already loaded."


class PackNotFoundError(RegistryError):
    """A requested pack was not found."""

    code = "pack_not_found"
    message = "Pack not found."


class ActionNotFoundError(RegistryError):
    """A requested action was not found in the registry."""

    code = "action_not_found"
    message = "Action not found."


class PackConflictError(RegistryError):
    """A pack conflicts with already-loaded packs or the active registry."""

    code = "pack_conflict"
    message = "Pack conflicts with existing registrations."


class ManifestValidationError(RegistryError):
    """A manifest file failed schema validation."""

    code = "manifest_validation_error"
    message = "Manifest validation failed."


class HandlerNotFoundError(RegistryError):
    """No executor handler is registered for an action."""

    code = "handler_not_found"
    message = "No handler registered for action."


__all__ = [
    "RegistryError",
    "DuplicateActionError",
    "DuplicatePackError",
    "PackNotFoundError",
    "ActionNotFoundError",
    "PackConflictError",
    "ManifestValidationError",
    "HandlerNotFoundError",
]
