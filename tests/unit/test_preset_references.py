# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the preset variable reference grammar parser."""

from __future__ import annotations

import pytest

from ambrosia.presets.errors import InvalidReferenceError
from ambrosia.presets.references import (
    VariableReference,
    parse_reference,
    step_id_from_steps_reference,
)

_VALID = [
    ("{{ inputs.target }}", "inputs", ("inputs", "target")),
    (
        "{{ context.selected_target.address }}",
        "context",
        ("context", "selected_target", "address"),
    ),
    (
        "{{ artifacts.550e8400-e29b-41d4-a716-446655440000.value.hostname }}",
        "artifacts",
        (
            "artifacts",
            "550e8400-e29b-41d4-a716-446655440000",
            "value",
            "hostname",
        ),
    ),
    (
        "{{ steps.discover.outputs.services }}",
        "steps",
        ("steps", "discover", "outputs", "services"),
    ),
    ("{{ secrets.vault.db_password }}", "secrets", ("secrets", "vault", "db_password")),
    (
        "{{ preset.metadata.name }}",
        "preset",
        ("preset", "metadata", "name"),
    ),
    ("{{  inputs.target  }}", "inputs", ("inputs", "target")),
]


def test_parse_all_namespaces() -> None:
    for token, namespace, path in _VALID:
        ref = parse_reference(token)
        assert isinstance(ref, VariableReference)
        assert ref.namespace == namespace
        assert ref.path == path
        assert ref.raw == token


def test_steps_reference_step_id_extraction() -> None:
    ref = parse_reference("{{ steps.network.discover.outputs.services }}")
    assert step_id_from_steps_reference(ref) == "network.discover"
    ref = parse_reference("{{ steps.discover.outputs.services }}")
    assert step_id_from_steps_reference(ref) == "discover"


_INVALID = [
    None,
    123,
    "not a reference",
    "prefix {{ inputs.target }}",
    "{{ inputs.target }} suffix",
    "{{ }}",
    "{{   }}",
    "{{ unknown.ns.path }}",
    "{{ steps.discover }}",
    "{{ steps.outputs.x }}",
    "{{ artifacts }}",
    "{{ secrets }}",
    "{{ inputs }}",
    "{{ context }}",
    "{{ preset }}",
]


def test_invalid_references_rejected() -> None:
    for token in _INVALID:
        with pytest.raises(InvalidReferenceError):
            parse_reference(token)  # type: ignore[arg-type]


def test_parse_reference_round_trip() -> None:
    ref = parse_reference("{{ inputs.target }}")
    assert str(ref) == "{{ inputs.target }}"
    assert ref.namespace == "inputs"
