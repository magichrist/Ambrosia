"""Preset system errors and structured resolution requests.

Exceptions in this module are raised when a preset document cannot be loaded,
validated, or planned. The structured resolution requests
(:class:`InputRequest`, :class:`ArtifactSelectionRequest`) are NOT errors:
they are typed values the engine returns so a TUI or CLI can surface them to
the operator in a structured form (typed input form, artifact picker).

:class:`SecretHandle` is an opaque reference to secret material. It never
carries plaintext and is the only value a ``secrets.*`` reference can resolve
to at the preset layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ambrosia.domain.errors import AmbrosiaError


class PresetError(AmbrosiaError):
    """Base error for preset loading, validation, planning, and resolution."""

    code = "preset_error"
    message = "Preset operation failed."


class PresetValidationError(PresetError):
    """A preset document failed structural or semantic validation."""

    code = "preset_validation_error"
    message = "Preset validation failed."


class DuplicateStepIdError(PresetValidationError):
    """Two or more steps declare the same step id."""

    code = "duplicate_step_id"
    message = "Duplicate step id."


class CyclicDependencyError(PresetValidationError):
    """Step dependencies (``needs`` or output references) contain a cycle."""

    code = "cyclic_dependency"
    message = "Step dependency graph contains a cycle."


class UnresolvedActionError(PresetValidationError):
    """An action step references an action id that is not registered."""

    code = "unresolved_action"
    message = "Referenced action is not registered."


class InvalidReferenceError(PresetValidationError):
    """A variable reference or output binding could not be parsed or resolved."""

    code = "invalid_reference"
    message = "Invalid variable reference."


class InvalidPredicateError(PresetValidationError):
    """A ``when``/visibility predicate is outside the constrained grammar."""

    code = "invalid_predicate"
    message = "Invalid predicate."


class TypeMismatchError(PresetValidationError):
    """A resolved value does not match the declared type of its destination."""

    code = "type_mismatch"
    message = "Resolved value does not match the expected type."


@dataclass(frozen=True)
class InputRequest:
    """A required preset input that has no resolved value yet.

    The TUI or CLI can render this as a typed input form. It never contains
    secret material.
    """

    input_id: str
    type: str
    required: bool = True
    source: str = "context_or_user"
    hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "input_request",
            "input_id": self.input_id,
            "type": self.type,
            "required": self.required,
            "source": self.source,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class ArtifactSelectionRequest:
    """The operator must choose among multiple matching artifacts.

    Returned when a constrained artifact selection matches more than one
    candidate. ``candidates`` carries artifact ids only (safe, non-secret
    identifiers suitable for rendering a picker).
    """

    artifact_type: str
    where: dict[str, object] | None = None
    target_ref: str | None = None
    candidates: tuple[str, ...] = ()
    hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "artifact_selection_request",
            "artifact_type": self.artifact_type,
            "where": self.where,
            "target_ref": self.target_ref,
            "candidates": list(self.candidates),
            "hint": self.hint,
        }


@dataclass(frozen=True)
class SecretHandle:
    """Opaque handle to a secret managed by a :class:`SecretStore`.

    The preset layer never sees, logs, or returns the plaintext value. The
    executor layer exchanges the handle for a protected value through the
    secret provider at execution time.
    """

    ref: str
    provider: str | None = None

    def __repr__(self) -> str:
        return f"SecretHandle(ref={self.ref!r})"

    def to_dict(self) -> dict[str, object]:
        return {"kind": "secret_handle", "ref": self.ref}


@dataclass(frozen=True)
class ResolvedValue:
    """A successfully resolved, typed value."""

    value: Any


@dataclass(frozen=True)
class DeferredStepOutput:
    """An action step output that will be bound at execution time.

    Action outputs are not known until the step runs, so a reference to
    ``steps.<action_step>.outputs.<name>`` resolves to a deferred placeholder
    during planning/dry-run and is resolved by the execution layer later.
    """

    step_id: str
    output_name: str


# A complete resolution outcome for a single binding.
ResolutionResult = ResolvedValue | InputRequest | ArtifactSelectionRequest | DeferredStepOutput

__all__ = [
    "PresetError",
    "PresetValidationError",
    "DuplicateStepIdError",
    "CyclicDependencyError",
    "UnresolvedActionError",
    "InvalidReferenceError",
    "InvalidPredicateError",
    "TypeMismatchError",
    "InputRequest",
    "ArtifactSelectionRequest",
    "SecretHandle",
    "ResolvedValue",
    "DeferredStepOutput",
    "ResolutionResult",
]
