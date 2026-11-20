# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for preset dry-run: typed resolution, no executor invocation."""

from __future__ import annotations

from typing import Never

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.models import Artifact
from ambrosia.presets.errors import (
    ArtifactSelectionRequest,
    DeferredStepOutput,
    InputRequest,
    SecretHandle,
    TypeMismatchError,
)
from ambrosia.presets.loader import PresetLoader
from ambrosia.registry import Registry


class _TracingHandler:
    """Handler that raises if invoked: dry-runs must never execute actions."""

    async def execute(self, request: object, context: object) -> Never:  # type: ignore[no-untyped-def]
        raise AssertionError()


def _registry() -> Registry:
    registry = Registry()
    registry.register_builtin(
        ActionDefinition(
            id="net.discover",
            version="1.0.0",
            name="Discover",
            description="d",
            category="discovery",
            executor=ExecutorReference(kind="native"),
            effects=["network_observe"],
            input_schema={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "ports": {"type": "string"},
                },
                "required": ["target"],
            },
        ),
        handler=_TracingHandler(),
    )
    registry.register_builtin(
        ActionDefinition(
            id="net.read",
            version="1.0.0",
            name="Read",
            description="d",
            category="inventory",
            executor=ExecutorReference(kind="native"),
            effects=["local_read"],
        )
    )
    return registry


def _preset_text(steps: str, inputs: str = "") -> str:
    inputs_block = f"inputs:\n{inputs}" if inputs.strip() else "inputs: {}"
    return f"""\
api_version: ambrosia/v1
kind: preset
metadata:
  id: net.demo
  name: Demo
  version: 1.0.0
  description: d
{inputs_block}
steps:
{steps}
"""


def _load(registry: Registry, text: str) -> tuple[PresetLoader, object]:
    loader = PresetLoader(registry)
    loaded = loader.load_text(text)
    return loader, loaded


def test_dry_run_never_invokes_executor() -> None:
    loader, loaded = _load(
        _registry(),
        _preset_text(
            inputs="  target:\n    type: target.host\n    required: true\n",
            steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "{{ inputs.target }}"
""",
        ),
    )
    # No handler is invoked: this succeeds and resolves the binding.
    result = loader.dry_run(loaded.definition, loaded.plan, inputs={"target": "host.example.com"})
    assert result.resolved["discover"]["target"] == "host.example.com"
    assert result.errors == ()
    assert result.requests == ()


def test_dry_run_deterministic() -> None:
    registry = _registry()
    text = _preset_text(
        inputs="  target:\n    type: target.host\n    required: true\n",
        steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "{{ inputs.target }}"
  - id: publish
    type: output
    outputs:
      echoed:
        source: "{{ steps.discover.outputs.target }}"
""",
    )
    loader = PresetLoader(registry)
    loaded = loader.load_text(text)
    first = loader.dry_run(loaded.definition, loaded.plan, inputs={"target": "host.example.com"})
    second = loader.dry_run(loaded.definition, loaded.plan, inputs={"target": "host.example.com"})
    assert first.plan.order == second.plan.order
    assert first.plan.effects == second.plan.effects
    assert first.resolved == second.resolved
    assert first.active_steps == second.active_steps
    assert first.requests == second.requests
    assert first.errors == second.errors


def test_missing_required_input_surfaces_request() -> None:
    loader, loaded = _load(
        _registry(),
        _preset_text(
            inputs="  target:\n    type: target.host\n    required: true\n",
            steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "{{ inputs.target }}"
""",
        ),
    )
    result = loader.dry_run(loaded.definition, loaded.plan)
    assert len(result.requests) == 1
    request = result.requests[0]
    assert isinstance(request, InputRequest)
    assert request.input_id == "target"
    assert request.type == "target.host"
    # Typed, serializable form for the TUI/CLI.
    d = request.to_dict()
    assert d["kind"] == "input_request"
    assert d["input_id"] == "target"


def test_secret_resolves_to_opaque_handle() -> None:
    loader, loaded = _load(
        _registry(),
        _preset_text(
            inputs="  target:\n    type: target.host\n    required: true\n",
            steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "{{ inputs.target }}"
      password: "{{ secrets.vault.password }}"
""",
        ),
    )
    result = loader.dry_run(loaded.definition, loaded.plan, inputs={"target": "host.example.com"})
    value = result.resolved["discover"]["password"]
    assert isinstance(value, SecretHandle)
    assert value.ref == "vault.password"
    # The handle never reveals plaintext: only the opaque ref name is present.
    assert repr(value) == "SecretHandle(ref='vault.password')"
    assert value.to_dict() == {"kind": "secret_handle", "ref": "vault.password"}


def test_type_mismatch_recorded_as_error() -> None:
    loader, loaded = _load(
        _registry(),
        _preset_text(
            inputs="  port:\n    type: integer\n    required: true\n",
            steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "host.example.com"
      port: "{{ inputs.port }}"
""",
        ),
    )
    result = loader.dry_run(loaded.definition, loaded.plan, inputs={"port": "not-a-number"})
    assert len(result.errors) == 1
    error = result.errors[0]
    assert isinstance(error, TypeMismatchError)
    assert error.code == "type_mismatch"
    assert error.details["input"] == "port"
    assert error.details["expected_type"] == "integer"
    assert error.details["actual_type"] == "string"


def test_condition_gating_excludes_branch() -> None:
    loader, loaded = _load(
        _registry(),
        _preset_text(
            inputs="  target:\n    type: target.host\n    required: true\n",
            steps="""\
  - id: cond
    type: condition
    when:
      kind: artifact_exists
      artifact_type: network.service
      where:
        service: smb
    then:
      - publish
  - id: publish
    type: output
    outputs:
      next_actions:
        source: "{{ steps.cond.outputs.result }}"
""",
        ),
    )
    # No smb artifact: condition false, branch inactive.
    result = loader.dry_run(
        loaded.definition,
        loaded.plan,
        inputs={"target": "host.example.com"},
        artifacts={},
    )
    assert "publish" not in result.resolved
    assert "publish" not in result.active_steps
    assert result.condition_results == {"cond": False}

    smb = Artifact(
        id="s1",
        engagement_id="eng",
        type="network.service",
        value={"service": "smb", "port": 445},
        target_ref="host.example.com",
    )
    result = loader.dry_run(
        loaded.definition,
        loaded.plan,
        inputs={"target": "host.example.com"},
        artifacts={"s1": smb},
    )
    assert result.condition_results == {"cond": True}
    assert "publish" in result.active_steps
    assert result.step_outputs["publish"]["next_actions"] is True


def test_step_output_reference_to_action_is_deferred() -> None:
    loader, loaded = _load(
        _registry(),
        _preset_text(
            inputs="  target:\n    type: target.host\n    required: true\n",
            steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "{{ inputs.target }}"
  - id: later
    type: action
    action: net.discover
    needs: [discover]
    inputs:
      target: "{{ steps.discover.outputs.target }}"
""",
        ),
    )
    result = loader.dry_run(loaded.definition, loaded.plan, inputs={"target": "host.example.com"})
    assert result.errors == ()
    deferred = result.resolved["later"]["target"]
    assert isinstance(deferred, DeferredStepOutput)
    assert deferred.step_id == "discover"


def test_artifact_selection_request_on_ambiguity() -> None:
    registry = _registry()
    loader = PresetLoader(registry)
    loader.load_text(
        _preset_text(
            inputs="",
            steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "host.example.com"
""",
        )
    )
    from ambrosia.presets.resolution import ResolutionContext, Resolver

    a1 = Artifact(
        id="a1",
        engagement_id="eng",
        type="network.service",
        value={"service": "smb"},
        target_ref="host.example.com",
    )
    a2 = Artifact(
        id="a2",
        engagement_id="eng",
        type="network.service",
        value={"service": "smb"},
        target_ref="host.example.com",
    )

    context = ResolutionContext(
        inputs={},
        context={},
        target={},
        artifacts={"a1": a1, "a2": a2},
        step_outputs={},
        preset={},
        declared_inputs={},
    )
    resolver = Resolver(context=context)
    picked = resolver.resolve_artifact_selection(
        artifact_type="network.service", where={"service": "smb"}
    )
    assert isinstance(picked, ArtifactSelectionRequest)
    assert picked.candidates == ("a1", "a2")
    assert picked.artifact_type == "network.service"
    assert picked.to_dict()["kind"] == "artifact_selection_request"
