# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the constrained predicate grammar."""

from __future__ import annotations

import pytest

from ambrosia.domain.models import Artifact
from ambrosia.presets.errors import InvalidPredicateError
from ambrosia.presets.predicates import Predicate, evaluate_predicate, parse_predicate


def _artifact(artifact_id: str, artifact_type: str, value: dict[str, object]) -> Artifact:
    return Artifact(
        id=artifact_id,
        engagement_id="eng",
        type=artifact_type,
        value=value,
    )


def _artifacts(*items: tuple[str, str, dict[str, object]]) -> list[Artifact]:
    return [_artifact(id_, type_, value) for id_, type_, value in items]


def test_parse_artifact_exists() -> None:
    predicate = parse_predicate(
        {
            "kind": "artifact_exists",
            "artifact_type": "network.service",
            "where": {"service": "smb"},
        }
    )
    assert predicate == Predicate(
        kind="artifact_exists",
        artifact_type="network.service",
        where={"service": "smb"},
    )


def test_parse_artifact_field_equals() -> None:
    predicate = parse_predicate(
        {
            "kind": "artifact_field_equals",
            "artifact_type": "network.service",
            "field": "service",
            "value": "smb",
        }
    )
    assert predicate.kind == "artifact_field_equals"
    assert predicate.value == "smb"


def test_parse_input_present() -> None:
    predicate = parse_predicate({"kind": "input_present", "input": "target"})
    assert predicate == Predicate(kind="input_present", input="target")


def test_parse_predicate_rejects_unknown_kind() -> None:
    with pytest.raises(InvalidPredicateError):
        parse_predicate({"kind": "always_true"})


def test_parse_predicate_rejects_references() -> None:
    with pytest.raises(InvalidPredicateError):
        parse_predicate(
            {
                "kind": "artifact_field_equals",
                "artifact_type": "network.service",
                "field": "service",
                "value": "{{ inputs.target }}",
            }
        )


def test_parse_predicate_rejects_non_literal_value() -> None:
    with pytest.raises(InvalidPredicateError):
        parse_predicate(
            {
                "kind": "artifact_field_equals",
                "artifact_type": "network.service",
                "field": "port",
                "value": [1, 2],
            }
        )


def test_parse_predicate_rejects_missing_fields() -> None:
    with pytest.raises(InvalidPredicateError):
        parse_predicate({"kind": "input_present"})


def test_evaluate_artifact_exists() -> None:
    artifacts = _artifacts(
        ("a1", "network.service", {"service": "smb", "port": 445}),
        ("a2", "network.service", {"service": "http", "port": 80}),
    )
    predicate = parse_predicate(
        {"kind": "artifact_exists", "artifact_type": "network.service"}
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is True

    predicate = parse_predicate(
        {
            "kind": "artifact_exists",
            "artifact_type": "network.service",
            "where": {"service": "smb"},
        }
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is True

    predicate = parse_predicate(
        {
            "kind": "artifact_exists",
            "artifact_type": "network.service",
            "where": {"service": "rdp"},
        }
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is False

    predicate = parse_predicate(
        {"kind": "artifact_exists", "artifact_type": "windows.domain"}
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is False


def test_evaluate_artifact_field_equals() -> None:
    artifacts = _artifacts(
        ("a1", "network.service", {"service": "smb", "port": 445}),
        ("a2", "network.service", {"service": "http", "port": 80}),
    )
    predicate = parse_predicate(
        {
            "kind": "artifact_field_equals",
            "artifact_type": "network.service",
            "field": "service",
            "value": "smb",
        }
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is True

    predicate = parse_predicate(
        {
            "kind": "artifact_field_equals",
            "artifact_type": "network.service",
            "field": "port",
            "value": 445,
        }
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is True

    predicate = parse_predicate(
        {
            "kind": "artifact_field_equals",
            "artifact_type": "network.service",
            "field": "service",
            "value": "rdp",
        }
    )
    assert evaluate_predicate(predicate, artifacts=artifacts, inputs={}) is False


def test_evaluate_input_present() -> None:
    predicate = parse_predicate({"kind": "input_present", "input": "target"})
    assert evaluate_predicate(predicate, artifacts=[], inputs={"target": "host"}) is True
    assert evaluate_predicate(predicate, artifacts=[], inputs={}) is False

    predicate = parse_predicate({"kind": "input_present", "input": "missing"})
    assert evaluate_predicate(predicate, artifacts=[], inputs={"target": "host"}) is False
