"""Typed variable resolution for preset bindings.

Resolves references against the namespaces defined in
``docs/01_SHARED_CONTRACTS.md`` section 6:

* ``inputs.*`` -- operator-provided preset input values
* ``context.*`` -- current engagement context snapshot
* ``target.*`` -- selected or explicitly bound target
* ``artifacts.*`` -- artifacts by stable id, with field traversal
* ``steps.<step_id>.outputs.*`` -- output of an earlier step
* ``preset.*`` -- preset metadata
* ``secrets.*`` -- opaque :class:`~ambrosia.presets.errors.SecretHandle`
  instances only; plaintext is never available at this layer

Values are resolved as typed Python objects, never as implicitly coerced
strings. Missing required inputs yield :class:`InputRequest`; ambiguous
artifact selections yield :class:`ArtifactSelectionRequest`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

from ambrosia.domain.models import Artifact
from ambrosia.presets.errors import (
    ArtifactSelectionRequest,
    DeferredStepOutput,
    InputRequest,
    InvalidReferenceError,
    ResolutionResult,
    ResolvedValue,
    SecretHandle,
)
from ambrosia.presets.references import VariableReference

# JSON Schema primitive types understood structurally by the preset layer.
# Namespaced semantic types (e.g. ``target.host``, ``network.service``,
# ``port_list``) are validated by the domain/action layer, not here.
_PRIMITIVE_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


@dataclass(frozen=True)
class TypeMismatchInfo:
    """A resolved value does not match the declared type of its destination."""

    destination: str
    expected_type: str
    actual_type: str


@dataclass(frozen=True)
class ResolutionContext:
    """Immutable namespaces supplied to the resolver.

    All mappings are shallow copies of the caller's data; the resolver never
    mutates caller state. For a fixed context the resolver is deterministic.
    """

    inputs: dict[str, object] = field(default_factory=dict)
    context: dict[str, object] = field(default_factory=dict)
    target: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    step_outputs: dict[str, dict[str, object]] = field(default_factory=dict)
    preset: dict[str, object] = field(default_factory=dict)
    # Preset input id -> declared input declaration (read only via getattr).
    declared_inputs: Mapping[str, object] = field(default_factory=dict)
    # Preset input id -> declared type hint for structural type checking.
    input_type_hints: dict[str, str] = field(default_factory=dict)


def _actual_type_name(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def check_type(value: object, expected_type: str) -> TypeMismatchInfo | None:
    """Return a type mismatch info when ``value`` does not match ``expected_type``.

    Namespaced semantic types (``target.host``, ``network.service``,
    ``port_list``) are not structurally checked here.
    """
    expected = expected_type.strip().lower()
    allowed = _PRIMITIVE_TYPES.get(expected)
    if allowed is None:
        return None
    if expected in ("integer", "number") and isinstance(value, bool):
        return TypeMismatchInfo(destination="", expected_type=expected, actual_type="boolean")
    if not isinstance(value, allowed):
        return TypeMismatchInfo(
            destination="",
            expected_type=expected,
            actual_type=_actual_type_name(value),
        )
    return None


def _where_matches(artifact: Artifact, where: dict[str, object] | None) -> bool:
    if not where:
        return True
    return all(artifact.value.get(key) == value for key, value in where.items())


def _traverse(root: dict[str, object] | None, path: tuple[str, ...]) -> Any:
    """Traverse a plain dict namespace by path segments.

    Missing segments yield ``None`` (missing context data is not an error at
    the preset layer).
    """
    if not root:
        return None
    current: Any = root
    for segment in path[1:]:
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


class Resolver:
    """Resolves preset bindings to typed results against fixed namespaces.

    Side-effect free and deterministic: a fixed context always produces the
    same result. Never executes code; never touches secret plaintext.
    """

    def __init__(self, *, context: ResolutionContext) -> None:
        self._context = context

    # ------------------------------------------------------------------ public

    def resolve(self, binding: object) -> ResolutionResult:
        """Resolve one input binding to a typed result.

        ``binding`` is either a literal YAML value or a
        :class:`VariableReference`. The union result is one of:

        * :class:`ResolvedValue` -- a typed value
        * :class:`InputRequest` -- a required input is missing
        * :class:`ArtifactSelectionRequest` -- the operator must pick an artifact
        * :class:`DeferredStepOutput` -- an action output bound at execution time
        """
        if isinstance(binding, VariableReference):
            return self._resolve_reference(binding)
        if isinstance(binding, str) and binding.startswith("{{") and binding.endswith("}}"):
            # Non-token reference strings are rejected at load time; treat any
            # that reach here as opaque literals rather than interpolating.
            return ResolvedValue(value=binding)
        return ResolvedValue(value=binding)

    def resolve_artifact_selection(
        self,
        *,
        artifact_type: str,
        where: dict[str, object] | None = None,
        target_ref: str | None = None,
    ) -> Artifact | ArtifactSelectionRequest | None:
        """Select artifacts of a type, optionally constrained by ``where``.

        Returns the single matching artifact, an
        :class:`ArtifactSelectionRequest` when more than one candidate matches,
        or ``None`` when nothing matches.
        """
        candidates = [
            artifact
            for artifact in self._context.artifacts.values()
            if artifact.type == artifact_type
            and (target_ref is None or artifact.target_ref == target_ref)
            and _where_matches(artifact, where)
        ]
        if len(candidates) == 0:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return ArtifactSelectionRequest(
            artifact_type=artifact_type,
            where=where,
            target_ref=target_ref,
            candidates=tuple(artifact.id for artifact in candidates),
        )

    # ------------------------------------------------------------------ private

    def _resolve_reference(self, ref: VariableReference) -> ResolutionResult:
        namespace = ref.namespace
        path = ref.path

        if namespace == "inputs":
            return self._resolve_inputs(path)
        if namespace == "context":
            return ResolvedValue(value=_traverse(self._context.context, path))
        if namespace == "target":
            return ResolvedValue(value=_traverse(self._context.target, path))
        if namespace == "artifacts":
            return self._resolve_artifact(path)
        if namespace == "steps":
            return self._resolve_step_output(path)
        if namespace == "secrets":
            return ResolvedValue(value=SecretHandle(ref=".".join(path[1:])))
        if namespace == "preset":
            return ResolvedValue(value=_traverse(self._context.preset, path))
        raise InvalidReferenceError(f"unknown namespace {namespace!r}")  # pragma: no cover  # noqa: TRY003

    def _resolve_inputs(self, path: tuple[str, ...]) -> ResolutionResult:
        if len(path) < 2:
            raise InvalidReferenceError("inputs requires a name segment")  # noqa: TRY003
        name = ".".join(path[1:])
        provided = self._context.inputs
        if name in provided:
            return ResolvedValue(value=provided[name])
        declaration = self._context.declared_inputs.get(name)
        if declaration is not None:
            required = bool(getattr(declaration, "required", False))
            default = getattr(declaration, "default", None)
            has_default = default is not None
            if required and not has_default:
                return InputRequest(
                    input_id=name,
                    type=str(getattr(declaration, "type", "object")),
                    required=True,
                    source=str(getattr(declaration, "source", "context_or_user")),
                    hint=(
                        "provide a value for preset input "
                        f"{name!r} (type {getattr(declaration, 'type', 'object')})"
                    ),
                )
            if has_default:
                return ResolvedValue(value=default)
        return ResolvedValue(value=None)

    def _resolve_artifact(self, path: tuple[str, ...]) -> ResolutionResult:
        if len(path) < 2:
            raise InvalidReferenceError("artifacts requires an artifact id")  # noqa: TRY003
        artifact_id = path[1]
        artifact = self._context.artifacts.get(artifact_id)
        if artifact is None:
            raise InvalidReferenceError(  # noqa: TRY003
                f"unknown artifact id {artifact_id!r} in artifacts reference"
            )
        current: Any = artifact
        for segment in path[2:]:
            if segment == "value" and isinstance(current, Artifact):
                current = current.value
            elif isinstance(current, dict):
                current = current.get(segment)
            else:
                return ResolvedValue(value=None)
        return ResolvedValue(value=current)

    def _resolve_step_output(self, path: tuple[str, ...]) -> ResolutionResult:
        # steps.<step_id>.outputs.<output>...
        outputs_indexes = [index for index, segment in enumerate(path) if segment == "outputs"]
        if not outputs_indexes:
            raise InvalidReferenceError(  # noqa: TRY003
                f"invalid steps reference {'.'.join(path)!r}: expected "
                "steps.<step_id>.outputs.<output>"
            )
        marker = outputs_indexes[0]
        step_id = ".".join(path[1:marker])
        output_segments = path[marker + 1 :]
        outputs = self._context.step_outputs.get(step_id, {})
        if not output_segments:
            return ResolvedValue(value=outputs or None)
        current: Any = outputs
        for segment in output_segments:
            if isinstance(current, dict):
                current = current.get(segment)
            else:
                return ResolvedValue(value=None)
        if current is None:
            # Action outputs are bound by the execution layer, not at plan time.
            return DeferredStepOutput(step_id=step_id, output_name=output_segments[0])
        return ResolvedValue(value=current)


__all__ = [
    "TypeMismatchInfo",
    "ResolutionContext",
    "DeferredStepOutput",
    "ResolvedValue",
    "check_type",
    "Resolver",
]
