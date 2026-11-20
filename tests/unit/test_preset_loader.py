# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for preset loading and validation (safe YAML, no code execution)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.errors import ParseError
from ambrosia.presets.errors import (
    CyclicDependencyError,
    DuplicateStepIdError,
    InvalidPredicateError,
    InvalidReferenceError,
    PresetValidationError,
    UnresolvedActionError,
)
from ambrosia.presets.loader import PresetLoader
from ambrosia.registry import Registry

if TYPE_CHECKING:
    from pathlib import Path


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
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
        )
    )
    return registry


def _preset_text(extra: str = "", steps: str = "") -> str:
    return f"""\
api_version: ambrosia/v1
kind: preset
metadata:
  id: net.demo
  name: Demo
  version: 1.0.0
  description: d
{extra}
steps:
{steps}
"""


def _step_text(step_id: str, action: str = "net.discover") -> str:
    return f"""\
  - id: {step_id}
    type: action
    action: {action}
    inputs:
      target: "{{ inputs.target }}"
"""


def test_valid_preset_loads() -> None:
    loader = PresetLoader(_registry())
    loaded = loader.load_text(_preset_text(steps=_step_text("discover")))
    assert loaded.definition.metadata.id == "net.demo"
    assert loaded.plan.order == ("discover",)
    assert loaded.plan.effects == frozenset({"network_observe"})


def test_json_preset_loads() -> None:
    loader = PresetLoader(_registry())
    text = """\
{
  "api_version": "ambrosia/v1",
  "kind": "preset",
  "metadata": {"id": "net.demo", "name": "Demo", "version": "1.0.0", "description": "d"},
  "inputs": {},
  "steps": [
    {"id": "discover", "type": "action", "action": "net.discover", "inputs": {}}
  ]
}"""
    loaded = loader.load_text(text)
    assert loaded.plan.order == ("discover",)


def test_invalid_yaml_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text("api_version: [unclosed")
    except ParseError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_python_object_tag_rejected() -> None:
    # No arbitrary Python object deserialization from YAML.
    loader = PresetLoader(_registry())
    try:
        loader.load_text(
            "api_version: ambrosia/v1\nkind: preset\nmetadata: !!python/object/apply:os.system [echo pwned]\nsteps: []\n"
        )
    except ParseError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_unknown_field_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(_preset_text(extra="bogus_field: true", steps=_step_text("discover")))
    except PresetValidationError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_unknown_step_field_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(
            _preset_text(
                steps="""\
  - id: discover
    type: action
    action: net.discover
    actin: net.discover
"""
            )
        )
    except PresetValidationError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_wrong_api_version_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(
            _preset_text().replace("api_version: ambrosia/v1", "api_version: ambrosia/v2")
        )
    except PresetValidationError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_duplicate_step_ids_via_loader_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(
            _preset_text(
                steps=_step_text("discover") + _step_text("discover", action="net.discover")
            )
        )
    except DuplicateStepIdError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_cycle_via_loader_rejected() -> None:
    loader = PresetLoader(_registry())
    text = _preset_text(
        steps="""\
  - id: a
    type: action
    action: net.discover
    needs: [b]
  - id: b
    type: action
    action: net.discover
    needs: [a]
"""
    )
    try:
        loader.load_text(text)
    except CyclicDependencyError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_unresolved_action_via_loader_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(_preset_text(steps=_step_text("discover", action="net.missing")))
    except UnresolvedActionError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_invalid_reference_syntax_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(
            _preset_text(
                steps="""\
  - id: discover
    type: action
    action: net.discover
    inputs:
      target: "not a reference {{ x }}"
"""
            )
        )
    except InvalidReferenceError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_invalid_predicate_rejected() -> None:
    loader = PresetLoader(_registry())
    try:
        loader.load_text(
            _preset_text(
                steps="""\
  - id: cond
    type: condition
    when:
      kind: not_a_predicate
"""
            )
        )
    except InvalidPredicateError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_then_else_branches_loaded() -> None:
    loader = PresetLoader(_registry())
    text = _preset_text(
        steps="""\
  - id: cond
    type: condition
    when:
      kind: input_present
      input: target
    then:
      - then_step
    else:
      - else_step
  - id: then_step
    type: output
  - id: else_step
    type: output
"""
    )
    loaded = loader.load_text(text)
    cond = loaded.plan.steps["cond"]
    assert cond.then == ("then_step",)
    assert cond.else_ == ("else_step",)
    assert loaded.plan.steps["then_step"].gated_by == "cond"
    assert loaded.plan.steps["else_step"].gated_by == "cond"


def test_load_file(tmp_path: Path) -> None:
    loader = PresetLoader(_registry())
    path = tmp_path / "preset.yaml"
    path.write_text(_preset_text(steps=_step_text("discover")), encoding="utf-8")
    loaded = loader.load_file(path)
    assert loaded.plan.order == ("discover",)
