"""Validation of action definitions, executor references, and declarations.

All checks are pure functions. No tools are executed and no side effects occur.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ambrosia.domain.action import (
        ActionDefinition,
        ArtifactRequirement,
        ExecutorReference,
        ToolDependency,
    )

# IDs are lowercase namespaced, dot-separated strings with at least two segments.
# Segments may contain lowercase letters, digits, and underscores (e.g.
# ``network.nmap.service_discovery``).
_ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[a-z0-9.-]+)?$")

# Effect classes named in the shared contracts (docs/00_MASTER_PLAN.md 10.2).
_KNOWN_EFFECTS = {
    "local_read",
    "local_write",
    "local_script",
    "network_observe",
    "remote_read",
    "authentication",
    "remote_change",
    "credential_access",
    "unknown",
}


class ValidationResult:
    """Outcome of a validation pass."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def validate_action_id(action_id: str) -> list[str]:
    """Validate a namespaced action ID format."""
    problems: list[str] = []
    if not _ID_RE.match(action_id or ""):
        problems.append(
            f"action id {action_id!r} must be lowercase dot-separated segments "
            f"(e.g. network.nmap.service_discovery)"
        )
    return problems


def validate_version(version: str) -> list[str]:
    """Validate a semantic version string."""
    problems: list[str] = []
    if not _VERSION_RE.match(version or ""):
        problems.append(f"version {version!r} must be semantic (e.g. 1.0.0)")
    return problems


def validate_executor_reference(executor: ExecutorReference) -> list[str]:
    """Validate an executor reference's internal consistency."""
    problems: list[str] = []
    kind = executor.kind

    if kind == "process":
        if not executor.executable:
            problems.append("process executor requires an executable name")
        if executor.script_asset:
            problems.append("process executor must not declare script_asset")
    elif kind == "script":
        if not executor.script_asset:
            problems.append("script executor requires a script_asset")
        if not executor.interpreter:
            problems.append("script executor requires an interpreter")
        if executor.executable:
            problems.append("script executor must not declare executable")
    elif kind == "native":
        if executor.executable or executor.script_asset or executor.interpreter:
            problems.append("native executor must not declare executable/script_asset/interpreter")
    elif kind == "external_plugin":
        if not executor.executable:
            problems.append("external_plugin executor requires an executable id")

    return problems


def validate_dependency(dep: ToolDependency) -> list[str]:
    """Validate a tool dependency declaration (metadata only)."""
    problems: list[str] = []
    if not dep.name or not dep.name.strip():
        problems.append("dependency name must not be empty")
    if dep.check_command is not None and not dep.check_command:
        problems.append("dependency check_command must be a non-empty list when provided")
    return problems


def validate_effects(effects: Iterable[str]) -> list[str]:
    """Validate declared effect classes.

    Unknown effects are not silently accepted; they produce a warning so the
    operator can review them rather than failing hard on future effect classes.
    """
    problems: list[str] = []
    for effect in effects:
        if effect not in _KNOWN_EFFECTS:
            problems.append(f"unknown effect class {effect!r}")
    return problems


def validate_artifact_requirement(req: ArtifactRequirement) -> list[str]:
    """Validate an artifact requirement declaration."""
    problems: list[str] = []
    if not req.type or not req.type.strip():
        problems.append("artifact requirement type must not be empty")
    return problems


def validate_action_definition(definition: ActionDefinition) -> ValidationResult:
    """Validate a complete action definition.

    Checks: ID format, version, executor reference, dependency declarations,
    effects, artifact requirements, and output type names.
    """
    result = ValidationResult()

    result.errors.extend(validate_action_id(definition.id))
    result.errors.extend(validate_version(definition.version))
    result.errors.extend(validate_executor_reference(definition.executor))

    for dep in definition.dependencies:
        result.errors.extend(validate_dependency(dep))

    for req in definition.required_artifacts:
        result.errors.extend(validate_artifact_requirement(req))

    # Unknown effects are not silently accepted, but they are reported as
    # warnings so that future effect classes do not break validation outright.
    result.warnings.extend(validate_effects(definition.effects))

    for output_type in definition.output_artifact_types:
        if not output_type or not output_type.strip():
            result.errors.append("output artifact type must not be empty")

    if not definition.name or not definition.name.strip():
        result.errors.append("action name must not be empty")
    if not definition.description or not definition.description.strip():
        result.errors.append("action description must not be empty")

    return result


def check_duplicate_ids(definitions: Iterable[ActionDefinition]) -> list[str]:
    """Report duplicate action IDs within an iterable of definitions."""
    seen: dict[str, str] = {}
    problems: list[str] = []
    for definition in definitions:
        if definition.id in seen:
            problems.append(
                f"duplicate action id {definition.id!r} "
                f"(first seen in {seen[definition.id]}, again in {definition.id})"
            )
        else:
            seen[definition.id] = definition.id
    return problems


__all__ = [
    "ValidationResult",
    "validate_action_id",
    "validate_version",
    "validate_executor_reference",
    "validate_dependency",
    "validate_effects",
    "validate_artifact_requirement",
    "validate_action_definition",
    "check_duplicate_ids",
]
