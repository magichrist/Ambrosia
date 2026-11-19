"""Phase contract: user-defined organizational labels, not lifecycle state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Predicate(BaseModel):
    """A constrained phase-visibility predicate."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["artifact_exists", "artifact_field_equals", "input_present"]
    artifact_type: str | None = None
    where: dict[str, object] | None = None
    field: str | None = None
    value: object | None = None
    input: str | None = None


class PhaseDefinition(BaseModel):
    """A user-defined navigation/grouping label for actions and presets.

    A phase cannot mandate the next phase, mutate context, or grant permission.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    action_refs: list[str] = Field(default_factory=list)
    preset_refs: list[str] = Field(default_factory=list)
    visible_when: list[Predicate] = Field(default_factory=list)
    sort_order: int = Field(default=100)
