# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.
"""Unit tests for manifest/schema validation of action definitions."""

from __future__ import annotations

from ambrosia.domain.action import ActionDefinition
from ambrosia.registry import (
    ManifestValidationError,
    load_definition_from_mapping,
    load_pack_from_file,
    validate_action_definition,
)

VALID_ACTION = {
    "id": "unit.valid.action",
    "version": "1.0.0",
    "name": "Valid Action",
    "description": "A valid action definition.",
    "category": "discovery",
    "tags": ["discovery"],
    "platforms": ["linux"],
    "executor": {"kind": "native"},
    "effects": ["local_read"],
    "risk": "low",
    "input_schema": {"type": "object", "properties": {}, "required": []},
    "scope_fields": [],
    "approval_required": False,
}

VALID_PACK = {
    "api_version": "ambrosia/v1",
    "kind": "pack",
    "metadata": {"id": "valid-pack", "name": "Valid Pack", "version": "1.0.0"},
    "actions": [VALID_ACTION],
}


def test_valid_action_definition_passes() -> None:
    action = ActionDefinition.model_validate(VALID_ACTION)
    result = validate_action_definition(action)
    assert result.ok


def test_invalid_action_id_rejected() -> None:
    bad = dict(VALID_ACTION, id="Invalid ID!")
    try:
        load_definition_from_mapping(bad)
    except ManifestValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ManifestValidationError for bad id")


def test_invalid_version_rejected() -> None:
    bad = dict(VALID_ACTION, version="not-a-version")
    try:
        load_definition_from_mapping(bad)
    except ManifestValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ManifestValidationError for bad version")


def test_unknown_effect_warns() -> None:
    action = ActionDefinition.model_validate(dict(VALID_ACTION, effects=["time_travel"]))
    result = validate_action_definition(action)
    # unknown effects are warnings, not hard errors (future-proofing)
    assert any("time_travel" in w for w in result.warnings)


def test_process_executor_requires_executable() -> None:
    bad = dict(
        VALID_ACTION,
        id="unit.valid.noexec",
        executor={"kind": "process"},
    )
    try:
        load_definition_from_mapping(bad)
    except ManifestValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ManifestValidationError for process without executable")


def test_script_executor_requires_script_and_interpreter() -> None:
    bad = dict(
        VALID_ACTION,
        id="unit.valid.noscript",
        executor={"kind": "script"},
    )
    try:
        load_definition_from_mapping(bad)
    except ManifestValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ManifestValidationError for script without script_asset")


def test_unknown_field_rejected() -> None:
    bad = dict(VALID_ACTION, id="unit.valid.extra", extra_field="nope")
    try:
        load_definition_from_mapping(bad)
    except ManifestValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ManifestValidationError for unknown field")


def test_duplicate_ids_in_pack_rejected() -> None:
    pack = dict(VALID_PACK, metadata=dict(VALID_PACK["metadata"]))
    pack["actions"] = [VALID_ACTION, dict(VALID_ACTION, id="unit.valid.action")]
    from ambrosia.registry import PackConflictError, Registry

    registry = Registry()
    try:
        registry.load_pack(pack)
    except PackConflictError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected PackConflictError for duplicate ids in pack")


def test_load_pack_from_file(fixture_pack_path="tests/fixtures/packs/test_pack.yaml") -> None:
    definitions = load_pack_from_file(fixture_pack_path)
    assert len(definitions) == 3
    assert definitions[0].id == "test.scan.host"


def test_empty_manifest_rejected() -> None:
    try:
        load_definition_from_mapping({})
    except ManifestValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ManifestValidationError for empty manifest")
