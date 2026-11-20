"""Loading action definitions from built-in Python sources and safe manifest files.

Manifests are YAML/JSON documents validated into :class:`ActionDefinition`
models. Only :func:`yaml.safe_load` is used; no arbitrary Python constructors,
eval, exec, or unpickling is permitted.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]  # types-PyYAML stubs are not a project dependency

if TYPE_CHECKING:
    from typing import Any

    from ambrosia.registry import Registry

from ambrosia.domain.action import ActionDefinition
from ambrosia.domain.errors import ParseError
from ambrosia.registry.errors import ManifestValidationError
from ambrosia.registry.validation import validate_action_definition


def load_definition_from_mapping(data: dict[str, Any], source: str = "mapping") -> ActionDefinition:
    """Build and validate an :class:`ActionDefinition` from a plain mapping.

    ``source`` is only used for error messages. Unknown fields are rejected by
    the Pydantic model (``extra="forbid"``).
    """
    if not isinstance(data, dict):
        raise ManifestValidationError(  # noqa: TRY003
            f"{source}: manifest must be a mapping, got {type(data).__name__}"
        )

    try:
        definition = ActionDefinition.model_validate(data)
    except Exception as exc:  # pragma: no cover - pydantic raises ValidationError
        raise ManifestValidationError(f"{source}: invalid action definition: {exc}") from exc  # noqa: TRY003

    result = validate_action_definition(definition)
    if not result.ok:
        raise ManifestValidationError(  # noqa: TRY003
            f"{source}: {definition.id}: " + "; ".join(result.errors)
        )

    return definition


def load_definition_from_file(path: str | Path) -> ActionDefinition:
    """Load and validate a single action definition from a YAML manifest file."""
    path = Path(path)
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestValidationError(f"{source}: cannot read manifest: {exc}") from exc  # noqa: TRY003

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ParseError(f"{source}: invalid YAML: {exc}") from exc  # noqa: TRY003

    if data is None:
        raise ManifestValidationError(f"{source}: empty manifest")  # noqa: TRY003

    return load_definition_from_mapping(data, source=source)


def load_pack_from_mapping(data: dict[str, Any], source: str = "mapping") -> list[ActionDefinition]:
    """Load and validate all action definitions embedded in a pack manifest."""
    if not isinstance(data, dict):
        raise ManifestValidationError(f"{source}: pack manifest must be a mapping")  # noqa: TRY003

    kind = data.get("kind")
    if kind != "pack":
        raise ManifestValidationError(f"{source}: expected kind 'pack', got {kind!r}")  # noqa: TRY003

    raw_actions = data.get("actions", [])
    if not isinstance(raw_actions, list):
        raise ManifestValidationError(f"{source}: 'actions' must be a list")  # noqa: TRY003

    definitions: list[ActionDefinition] = []
    for index, item in enumerate(raw_actions):
        label = f"{source}[actions[{index}]]"
        definitions.append(load_definition_from_mapping(item, source=label))

    return definitions


def load_pack_from_file(path: str | Path) -> list[ActionDefinition]:
    """Load and validate a pack manifest YAML file."""
    path = Path(path)
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestValidationError(f"{source}: cannot read pack manifest: {exc}") from exc  # noqa: TRY003

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ParseError(f"{source}: invalid YAML: {exc}") from exc  # noqa: TRY003

    if data is None:
        raise ManifestValidationError(f"{source}: empty pack manifest")  # noqa: TRY003

    return load_pack_from_mapping(data, source=source)


def build_registry() -> Registry:
    """Build the production registry with built-in actions and built-in packs.

    This is the single startup path used by the CLI and TUI so that domain packs
    (notably the Windows assessment pack) are registered in every real
    application. Registration is metadata-only: registering an action or pack
    never executes a tool, resolves a secret, or runs an assessment.
    """
    # Imported lazily to avoid a cycle: the Windows pack imports ``Registry``
    # from ``ambrosia.registry`` at module import time.
    from ambrosia.actions.builtins import register_builtins
    from ambrosia.packs.windows_assessment import register_pack
    from ambrosia.registry import Registry

    registry = Registry()
    register_builtins(registry)
    register_pack(registry)
    return registry


__all__ = [
    "build_registry",
    "load_definition_from_mapping",
    "load_definition_from_file",
    "load_pack_from_mapping",
    "load_pack_from_file",
]
