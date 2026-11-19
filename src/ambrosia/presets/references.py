"""Typed variable reference grammar for preset bindings.

Grammar (v0.1): a complete binding token is ``{{ <namespace> <path> }}``,
for example:

    {{ inputs.target }}
    {{ context.selected_target.address }}
    {{ artifacts.550e8400-e29b-41d4-a716-446655440000.value.hostname }}
    {{ steps.discover.outputs.services }}
    {{ secrets.vault.db_password }}
    {{ preset.metadata.name }}

Only a complete ``{{...}}`` token may be substituted: free-form interpolation
(e.g. ``prefix {{ x }}``), transformation functions, imports, loops, and
arbitrary expressions are rejected. The parser never evaluates anything; it
only produces a :class:`VariableReference` describing *where* to look.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ambrosia.presets.errors import InvalidReferenceError

_REF_RE = re.compile(r"^\{\{\s*(?P<body>.+?)\s*\}\}$")

_NAMESPACES = frozenset(
    {
        "inputs",
        "context",
        "target",
        "artifacts",
        "steps",
        "secrets",
        "preset",
    }
)

_OUTPUTS_MARKER = "outputs"


@dataclass(frozen=True)
class VariableReference:
    """A parsed variable reference.

    ``namespace`` is one of ``inputs``, ``context``, ``target``,
    ``artifacts``, ``steps``, ``secrets``, ``preset``. ``path`` is the
    remaining dot-separated segments, interpreted by the resolver per
    namespace.
    """

    namespace: str
    path: tuple[str, ...]
    raw: str

    def __str__(self) -> str:
        return self.raw


def step_id_from_steps_reference(ref: VariableReference) -> str:
    """Return the step id referenced by a ``steps.<step_id>.outputs.*`` reference."""
    if ref.namespace != "steps":
        raise InvalidReferenceError(  # noqa: TRY003
            f"not a steps reference: {ref.raw!r}"
        )
    marker_indexes = [
        index for index, segment in enumerate(ref.path) if segment == "outputs"
    ]
    if not marker_indexes:
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid steps reference {ref.raw!r}: missing outputs marker"
        )
    return ".".join(ref.path[1 : marker_indexes[0]])


def parse_reference(token: object) -> VariableReference:
    """Parse a binding token into a :class:`VariableReference`.

    Raises :class:`InvalidReferenceError` if ``token`` is not a complete
    ``{{...}}`` reference, uses an unknown namespace, or is malformed for its
    namespace.
    """
    if not isinstance(token, str):
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: expected a {{...}} string token"
        )
    match = _REF_RE.match(token)
    if match is None:
        raise InvalidReferenceError(  # noqa: TRY003
            "invalid reference "
            f"{token!r}: references must be a complete {{...}} token "
            "(no free-form interpolation)"
        )
    body = match.group(1)
    if not body.strip():
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: empty reference body"
        )
    segments = tuple(part.strip() for part in body.split("."))
    if not segments or segments[0] not in _NAMESPACES:
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: unknown namespace "
            f"{segments[0]!r} (expected one of {sorted(_NAMESPACES)})"
        )

    namespace = segments[0]
    rest = segments[1:]

    if namespace == "steps":
        _validate_steps_reference(token, segments)
    elif namespace == "artifacts":
        if len(rest) < 1:
            raise InvalidReferenceError(  # noqa: TRY003
                f"invalid reference {token!r}: artifacts requires an artifact id"
            )
    elif namespace == "secrets":
        if len(rest) < 1:
            raise InvalidReferenceError(  # noqa: TRY003
                f"invalid reference {token!r}: secrets requires a secret name"
            )
    elif len(rest) < 1:
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: {namespace} requires a path"
        )

    return VariableReference(namespace=namespace, path=segments, raw=token)


def _validate_steps_reference(token: str, segments: tuple[str, ...]) -> None:
    """Validate ``steps.<step_id>.outputs.<output>...</reference>``.

    The step id may itself contain dot-separated segments, so the first
    ``outputs`` segment after the namespace marks the start of the output
    path. Step ids should therefore not contain a segment named ``outputs``.
    """
    outputs_indexes = [
        index for index, segment in enumerate(segments) if segment == _OUTPUTS_MARKER
    ]
    if not outputs_indexes:
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: steps references must be "
            f"steps.<step_id>.outputs.<output>"
        )
    marker = outputs_indexes[0]
    step_segments = segments[1:marker]
    output_segments = segments[marker + 1 :]
    if not step_segments:
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: steps requires a step id"
        )
    if not output_segments:
        raise InvalidReferenceError(  # noqa: TRY003
            f"invalid reference {token!r}: steps requires an output name"
        )
