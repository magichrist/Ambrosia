"""Preset contract: declarative YAML/JSON action workflow definitions.

Pydantic models are the authoritative parser/validator; YAML is only a
serialized representation. No arbitrary Python expressions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PresetInput(BaseModel):
    """A declared preset input."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    required: bool = False
    default: object | None = None
    source: Literal["context_or_user", "user", "context"] = "context_or_user"


class OutputBinding(BaseModel):
    """Publish a named preset output from existing context/artifacts/step output."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)  # reference expression, e.g. steps.discover.outputs.services


class PresetStep(BaseModel):
    """A single step within a preset."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    # Step type: action | condition | approval | output
    type: Literal["action", "condition", "approval", "output"] = "action"
    # For action steps: the registered action ID.
    action: str | None = None
    # Ordered dependencies on earlier step ids.
    needs: list[str] = Field(default_factory=list)
    # Constrained predicate (no arbitrary expressions).
    when: dict[str, object] | None = None
    # Typed input bindings for action steps.
    inputs: dict[str, object] = Field(default_factory=dict)
    # Named outputs published by this step.
    outputs: dict[str, OutputBinding] = Field(default_factory=dict)
    # Failure behavior.
    on_failure: Literal["stop", "continue"] = "stop"


class PresetMetadata(BaseModel):
    """Preset metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    author: str | None = None
    tags: list[str] = Field(default_factory=list)


class PresetDefinition(BaseModel):
    """An ambrosia/v1 preset document."""

    model_config = ConfigDict(extra="forbid")

    api_version: Literal["ambrosia/v1"] = "ambrosia/v1"
    kind: Literal["preset"] = "preset"
    metadata: PresetMetadata
    phase_refs: list[str] = Field(default_factory=list)
    inputs: dict[str, PresetInput] = Field(default_factory=dict)
    steps: list[PresetStep] = Field(default_factory=list)
    outputs: dict[str, OutputBinding] = Field(default_factory=dict)
