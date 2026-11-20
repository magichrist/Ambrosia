# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Contract tests for the preset system end-to-end through the public API.

Validates the sample discovery preset, deterministic planning, dry-run without
executor invocation, structured missing-input requests, and YAML safety.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.errors import ParseError
from ambrosia.domain.models import Artifact
from ambrosia.presets import InputRequest, PresetLoader, SecretHandle
from ambrosia.registry import Registry

BUILTIN_PRESET = (
    Path(__file__).resolve().parents[2] / "builtin_presets" / "network.basic-discovery.yaml"
)


def _registry() -> Registry:
    registry = Registry()
    registry.register_builtin(
        ActionDefinition(
            id="network.nmap.service_discovery",
            version="1.0.0",
            name="Service Discovery",
            description="Bounded read-only service discovery.",
            category="discovery",
            tags=["discovery", "network"],
            platforms=[],
            executor=ExecutorReference(kind="process", executable="nmap"),
            effects=["network_observe"],
            risk="low",
            scope_fields=["target"],
            input_schema={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "ports": {"type": "string"},
                },
                "required": ["target"],
            },
        )
    )
    return registry


def test_sample_discovery_preset_validates_and_plans() -> None:
    loader = PresetLoader(_registry())
    loaded = loader.load_file(BUILTIN_PRESET)
    assert loaded.definition.metadata.id == "network.basic-discovery"
    plan = loaded.plan
    # Deterministic topological order.
    assert plan.order == ("discover", "suggest_smb", "publish_smb")
    # Effect summary: union of step effects.
    assert plan.effects == frozenset({"network_observe"})
    assert plan.required_inputs == ("target",)
    # Condition and output steps carry no action.
    assert plan.steps["suggest_smb"].action_id is None
    assert plan.steps["publish_smb"].action_id is None
    # Output step is gated by the condition.
    assert plan.steps["publish_smb"].gated_by == "suggest_smb"


def test_sample_preset_dry_run_deterministic_no_executor() -> None:
    registry = _registry()
    loader = PresetLoader(registry)
    loaded = loader.load_file(BUILTIN_PRESET)

    artifacts = {
        "s1": Artifact(
            id="s1",
            engagement_id="eng",
            type="network.service",
            value={"service": "smb", "port": 445},
            target_ref="host.example.com",
        )
    }

    first = loader.dry_run(
        loaded.definition,
        loaded.plan,
        inputs={"target": "host.example.com"},
        artifacts=artifacts,
    )
    second = loader.dry_run(
        loaded.definition,
        loaded.plan,
        inputs={"target": "host.example.com"},
        artifacts=artifacts,
    )
    assert first.plan.order == second.plan.order
    assert first.plan.effects == second.plan.effects
    assert first.resolved == second.resolved
    assert first.active_steps == second.active_steps
    assert first.condition_results == second.condition_results
    assert first.errors == ()
    # The condition matched and the output step published its result.
    assert first.active_steps == ("discover", "publish_smb", "suggest_smb")
    assert first.step_outputs["publish_smb"]["next_actions"] is True
    # Secret handle: opaque, no plaintext anywhere in the result.
    assert all(
        not isinstance(value, SecretHandle) or "password" not in repr(value)
        for values in first.resolved.values()
        for value in values.values()
    )


def test_sample_preset_missing_input_surfaces_typed_request() -> None:
    loader = PresetLoader(_registry())
    loaded = loader.load_file(BUILTIN_PRESET)
    result = loader.dry_run(loaded.definition, loaded.plan)
    assert len(result.requests) == 1
    request = result.requests[0]
    assert isinstance(request, InputRequest)
    assert request.input_id == "target"
    assert request.type == "target.host"
    assert request.required is True
    # Typed, serializable surface for the TUI/CLI.
    payload = request.to_dict()
    assert payload == {
        "kind": "input_request",
        "input_id": "target",
        "type": "target.host",
        "required": True,
        "source": "context_or_user",
        "hint": request.hint,
    }


def test_invalid_yaml_rejected() -> None:
    loader = PresetLoader(_registry())
    with pytest.raises(ParseError):
        loader.load_text("api_version: [unclosed\n")


def test_python_object_tag_cannot_load() -> None:
    # No arbitrary code execution from YAML: object tags are rejected.
    loader = PresetLoader(_registry())
    document = (
        "api_version: ambrosia/v1\n"
        "kind: preset\n"
        "metadata: !!python/object/apply:os.system [echo pwned]\n"
        "steps: []\n"
    )
    with pytest.raises(Exception):  # noqa: B017 - asserting any load failure
        loader.load_text(document)
