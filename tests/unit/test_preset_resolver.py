# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the typed preset variable resolver."""

from __future__ import annotations

import pytest

from ambrosia.domain.models import Artifact
from ambrosia.domain.preset import PresetInput
from ambrosia.presets.errors import (
    ArtifactSelectionRequest,
    DeferredStepOutput,
    InputRequest,
    InvalidReferenceError,
    ResolvedValue,
    SecretHandle,
)
from ambrosia.presets.references import parse_reference
from ambrosia.presets.resolution import ResolutionContext, Resolver, check_type


def _context(**overrides: object) -> ResolutionContext:
    data = {
        "inputs": {},
        "context": {},
        "target": {},
        "artifacts": {},
        "step_outputs": {},
        "preset": {},
        "declared_inputs": {},
        "input_type_hints": {},
    }
    data.update(overrides)
    return ResolutionContext(**data)  # type: ignore[arg-type]


def _artifact(artifact_id: str, artifact_type: str, value: dict[str, object]) -> Artifact:
    return Artifact(
        id=artifact_id,
        engagement_id="eng",
        type=artifact_type,
        value=value,
    )


def test_resolve_inputs_provided() -> None:
    resolver = Resolver(context=_context(inputs={"port": 443}))
    result = resolver.resolve(parse_reference("{{ inputs.port }}"))
    assert isinstance(result, ResolvedValue)
    assert result.value == 443


def test_resolve_inputs_default() -> None:
    declaration = PresetInput(type="string", required=False, default="80,443")
    resolver = Resolver(
        context=_context(inputs={}, declared_inputs={"port": declaration})
    )
    result = resolver.resolve(parse_reference("{{ inputs.port }}"))
    assert isinstance(result, ResolvedValue)
    assert result.value == "80,443"


def test_resolve_inputs_missing_required_returns_request() -> None:
    declaration = PresetInput(type="target.host", required=True)
    resolver = Resolver(
        context=_context(inputs={}, declared_inputs={"target": declaration})
    )
    result = resolver.resolve(parse_reference("{{ inputs.target }}"))
    assert isinstance(result, InputRequest)
    assert result.input_id == "target"
    assert result.type == "target.host"
    assert result.required is True
    assert "target" in result.hint


def test_resolve_inputs_missing_optional_without_default() -> None:
    declaration = PresetInput(type="string", required=False)
    resolver = Resolver(
        context=_context(inputs={}, declared_inputs={"target": declaration})
    )
    result = resolver.resolve(parse_reference("{{ inputs.target }}"))
    assert isinstance(result, ResolvedValue)
    assert result.value is None


def test_resolve_context_and_target() -> None:
    resolver = Resolver(
        context=_context(
            context={"selected_target": {"address": "10.0.0.1", "kind": "ip"}},
            target={"address": "10.0.0.1"},
        )
    )
    assert resolver.resolve(parse_reference("{{ context.selected_target.address }}")).value == "10.0.0.1"
    assert resolver.resolve(parse_reference("{{ target.address }}")).value == "10.0.0.1"
    assert resolver.resolve(parse_reference("{{ context.missing.deep }}")).value is None


def test_resolve_artifact_by_id_and_field() -> None:
    artifact = _artifact("a1", "network.host", {"hostname": "host", "address": "10.0.0.1"})
    resolver = Resolver(context=_context(artifacts={"a1": artifact}))
    result = resolver.resolve(parse_reference("{{ artifacts.a1 }}"))
    assert isinstance(result, ResolvedValue) and result.value is artifact
    result = resolver.resolve(parse_reference("{{ artifacts.a1.value.hostname }}"))
    assert isinstance(result, ResolvedValue) and result.value == "host"
    result = resolver.resolve(parse_reference("{{ artifacts.a1.value.missing }}"))
    assert isinstance(result, ResolvedValue) and result.value is None


def test_resolve_unknown_artifact_rejected() -> None:
    resolver = Resolver(context=_context())
    with pytest.raises(InvalidReferenceError):
        resolver.resolve(parse_reference("{{ artifacts.missing.value.x }}"))


def test_resolve_step_output_condition() -> None:
    resolver = Resolver(
        context=_context(step_outputs={"check": {"result": True}})
    )
    result = resolver.resolve(parse_reference("{{ steps.check.outputs.result }}"))
    assert isinstance(result, ResolvedValue) and result.value is True


def test_resolve_action_step_output_deferred() -> None:
    # Action outputs are bound by the execution layer, not at plan time.
    resolver = Resolver(context=_context())
    result = resolver.resolve(parse_reference("{{ steps.discover.outputs.services }}"))
    assert isinstance(result, DeferredStepOutput)
    assert result.step_id == "discover"
    assert result.output_name == "services"


def test_resolve_secret_opaque_handle() -> None:
    resolver = Resolver(context=_context())
    result = resolver.resolve(parse_reference("{{ secrets.vault.db_password }}"))
    assert isinstance(result, ResolvedValue)
    handle = result.value
    assert isinstance(handle, SecretHandle)
    assert handle.ref == "vault.db_password"
    # The handle never reveals plaintext: only the opaque ref name is present.
    assert repr(handle) == "SecretHandle(ref='vault.db_password')"
    assert handle.to_dict() == {"kind": "secret_handle", "ref": "vault.db_password"}


def test_resolve_preset_metadata() -> None:
    resolver = Resolver(
        context=_context(preset={"metadata": {"id": "net.demo", "name": "Demo", "version": "1.0.0"}})
    )
    result = resolver.resolve(parse_reference("{{ preset.metadata.id }}"))
    assert isinstance(result, ResolvedValue) and result.value == "net.demo"


def test_resolve_literal() -> None:
    resolver = Resolver(context=_context())
    assert resolver.resolve("fixed string").value == "fixed string"
    assert resolver.resolve(42).value == 42
    assert resolver.resolve(True).value is True
    assert resolver.resolve(["a", "b"]).value == ["a", "b"]
    assert resolver.resolve({"k": 1}).value == {"k": 1}


def test_check_type_mismatches() -> None:
    assert check_type("hello", "string") is None
    assert check_type(42, "integer") is None
    assert check_type(True, "boolean") is None
    assert check_type(3.14, "number") is None
    assert check_type([], "array") is None
    assert check_type({}, "object") is None

    mismatch = check_type(42, "string")
    assert mismatch is not None
    assert mismatch.expected_type == "string"
    assert mismatch.actual_type == "integer"

    mismatch = check_type("hello", "integer")
    assert mismatch is not None
    assert mismatch.actual_type == "string"

    # booleans are not numbers
    assert check_type(True, "number") is not None
    # semantic/namespaced types are not structurally checked
    assert check_type("host.example.com", "target.host") is None
    assert check_type(["80", "443"], "port_list") is None


def test_resolve_artifact_selection_none_one_many() -> None:
    artifacts = [
        _artifact("a1", "network.service", {"service": "smb"}),
        _artifact("a2", "network.service", {"service": "smb"}),
    ]
    resolver = Resolver(context=_context(artifacts={"a1": artifacts[0], "a2": artifacts[1]}))

    assert resolver.resolve_artifact_selection(artifact_type="windows.domain") is None
    result = resolver.resolve_artifact_selection(artifact_type="network.service")
    assert isinstance(result, ArtifactSelectionRequest)
    assert result.candidates == ("a1", "a2")

    single = [_artifact("a1", "network.service", {"service": "smb"})]
    resolver_single = Resolver(
        context=_context(artifacts={"a1": single[0]})
    )
    found = resolver_single.resolve_artifact_selection(artifact_type="network.service")
    assert isinstance(found, Artifact)
    assert found.id == "a1"
