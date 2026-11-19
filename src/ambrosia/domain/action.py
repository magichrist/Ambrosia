"""Action contract: immutable action metadata and availability result.

Separates action metadata from the Python handler implementation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolDependency(BaseModel):
    """Metadata describing a required local tool / runtime."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str | None = None
    # A metadata-only check; registry does not execute tools at import time.
    check_command: list[str] | None = None


class ArtifactRequirement(BaseModel):
    """An artifact type (and optional predicate) required for an action to apply."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    # Optional constrained predicate describing which artifact instances match.
    where: dict[str, object] | None = None
    # Whether the artifact must be bound to the same target as the action.
    same_target: bool = True


class ExecutorReference(BaseModel):
    """Reference to the executor that runs this action."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["native", "process", "script", "external_plugin"] = "process"
    # Fixed executable name or registered executable ID (for process actions).
    executable: str | None = None
    # Optional script asset reference + fixed interpreter ID.
    script_asset: str | None = None
    interpreter: str | None = None


class ActionDefinition(BaseModel):
    """Immutable metadata for a single reusable action."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)  # namespaced, e.g. network.nmap.service_discovery
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    phase_refs: list[str] = Field(default_factory=list)
    required_artifacts: list[ArtifactRequirement] = Field(default_factory=list)
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_artifact_types: list[str] = Field(default_factory=list)
    executor: ExecutorReference = Field(default_factory=ExecutorReference)
    dependencies: list[ToolDependency] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    risk: Literal["info", "low", "moderate", "high", "critical"] = "info"
    scope_fields: list[str] = Field(default_factory=list)
    approval_required: bool = False
    timeout_seconds: int = Field(default=60, ge=1)
    max_output_bytes: int = Field(default=2_000_000, ge=1)
    parser_refs: list[str] = Field(default_factory=list)


class ActionAvailability(BaseModel):
    """Pure matcher result: whether an action is currently usable and why."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1)
    status: Literal[
        "available",
        "needs_input",
        "needs_approval",
        "blocked",
        "missing_dependency",
        "not_applicable",
    ]
    reasons: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    matched_artifact_ids: list[str] = Field(default_factory=list)
    required_approval: bool = False
