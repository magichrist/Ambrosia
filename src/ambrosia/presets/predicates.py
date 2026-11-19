"""Constrained predicate grammar for preset ``when`` conditions.

Supported predicates (v0.1):

* ``artifact_exists`` -- at least one artifact of a type exists, optionally
  matching a ``where`` constraint on artifact value fields.
* ``artifact_field_equals`` -- at least one artifact of a type has a field
  equal to an enumerated literal value.
* ``input_present`` -- a preset input has been provided.

No ``eval``, arbitrary expressions, imports, loops, or unrestricted template
evaluation is permitted. Predicate values must be JSON literals; variable
references are not allowed inside predicates (that would be an expression).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ambrosia.presets.errors import InvalidPredicateError

if TYPE_CHECKING:
    from ambrosia.domain.models import Artifact

_PREDICATE_KINDS = frozenset(
    {"artifact_exists", "artifact_field_equals", "input_present"}
)

_LITERAL_TYPES = (str, int, float, bool, type(None))


@dataclass(frozen=True)
class Predicate:
    """A constrained predicate.

    ``kind`` is one of ``artifact_exists``, ``artifact_field_equals``,
    ``input_present``. The remaining fields are interpreted per kind:

    * ``artifact_exists``: ``artifact_type`` (+ optional ``where``)
    * ``artifact_field_equals``: ``artifact_type``, ``field``, ``value`` (literal)
    * ``input_present``: ``input``
    """

    kind: Literal["artifact_exists", "artifact_field_equals", "input_present"]
    artifact_type: str | None = None
    field: str | None = None
    value: object | None = None
    where: dict[str, object] | None = None
    input: str | None = None


def _is_literal(value: object) -> bool:
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        # A reference is an expression, not a literal.
        return False
    return isinstance(value, _LITERAL_TYPES)


def parse_predicate(raw: dict[str, object] | None) -> Predicate | None:
    """Parse a raw predicate mapping into a :class:`Predicate`.

    Raises :class:`InvalidPredicateError` for unknown kinds, missing fields,
    non-literal values, or references inside a predicate.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise InvalidPredicateError(  # noqa: TRY003
            f"predicate must be a mapping, got {type(raw).__name__}"
        )

    kind = raw.get("kind")
    if kind not in _PREDICATE_KINDS:
        raise InvalidPredicateError(  # noqa: TRY003
            f"unknown predicate kind {kind!r}; expected one of "
            f"{sorted(_PREDICATE_KINDS)}"
        )

    artifact_type = raw.get("artifact_type")
    field = raw.get("field")
    value = raw.get("value")
    where = raw.get("where")
    input_name = raw.get("input")

    if kind == "artifact_exists":
        if not isinstance(artifact_type, str) or not artifact_type:
            raise InvalidPredicateError(  # noqa: TRY003
                "artifact_exists requires a non-empty artifact_type"
            )
        if where is not None and not isinstance(where, dict):
            raise InvalidPredicateError("artifact_exists where must be a mapping")  # noqa: TRY003
        _validate_literals(where, "artifact_exists where")
        return Predicate(
            kind="artifact_exists",
            artifact_type=artifact_type,
            where=where,
        )

    if kind == "artifact_field_equals":
        if not isinstance(artifact_type, str) or not artifact_type:
            raise InvalidPredicateError(  # noqa: TRY003
                "artifact_field_equals requires a non-empty artifact_type"
            )
        if not isinstance(field, str) or not field:
            raise InvalidPredicateError(  # noqa: TRY003
                "artifact_field_equals requires a non-empty field"
            )
        if not _is_literal(value):
            raise InvalidPredicateError(  # noqa: TRY003
                "artifact_field_equals value must be a JSON literal "
                "(string, number, boolean, or null); references are not allowed"
            )
        return Predicate(
            kind="artifact_field_equals",
            artifact_type=artifact_type,
            field=field,
            value=value,
        )

    # input_present
    if not isinstance(input_name, str) or not input_name:
        raise InvalidPredicateError(  # noqa: TRY003
            "input_present requires a non-empty input name"
        )
    return Predicate(kind="input_present", input=input_name)


def _validate_literals(mapping: dict[str, object] | None, what: str) -> None:
    if not mapping:
        return
    for key, value in mapping.items():
        if not _is_literal(value):
            raise InvalidPredicateError(  # noqa: TRY003
                f"{what} value for key {key!r} must be a JSON literal; "
                "references are not allowed in predicates"
            )


def evaluate_predicate(
    predicate: Predicate,
    *,
    artifacts: list[Artifact],
    inputs: dict[str, object],
) -> bool:
    """Evaluate a parsed predicate against artifacts and provided inputs.

    Pure and deterministic: no I/O, no side effects.
    """
    if predicate.kind == "artifact_exists":
        return any(
            artifact.type == predicate.artifact_type
            and _where_matches(artifact, predicate.where)
            for artifact in artifacts
        )
    if predicate.kind == "artifact_field_equals":
        field = predicate.field
        if field is None:  # guarded by the parser, defensive here
            return False
        return any(
            artifact.type == predicate.artifact_type
            and artifact.value.get(field) == predicate.value
            for artifact in artifacts
        )
    # input_present
    return predicate.input in inputs


def _where_matches(artifact: Artifact, where: dict[str, object] | None) -> bool:
    if not where:
        return True
    return all(
        artifact.value.get(key) == value for key, value in where.items()
    )


__all__ = [
    "Predicate",
    "parse_predicate",
    "evaluate_predicate",
]
