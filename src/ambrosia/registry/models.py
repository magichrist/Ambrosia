"""Registry data models: pack manifests, load results, and read-only snapshots.

Pack manifests are the serialized (YAML/JSON) representation of a pack. Pydantic
models are the authoritative validator; the document format is only a carrier.

ContextSnapshot and PolicySnapshot are immutable, read-only views supplied to
the pure availability matcher. The matcher performs no I/O and has no side
effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from ambrosia.domain.action import (  # noqa: TC001
    ActionDefinition,  # imported at runtime so Pydantic can resolve PackManifest's forward reference
)

if TYPE_CHECKING:
    from ambrosia.domain.models import Artifact, Scope


class PackMetadata(BaseModel):
    """Metadata describing a pack."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""


class PackManifest(BaseModel):
    """A distributable pack of action definitions.

    ``api_version`` and ``kind`` follow the ``ambrosia/v1`` preset-style
    envelope so packs and presets share a single document grammar.
    """

    model_config = ConfigDict(extra="forbid")

    api_version: Literal["ambrosia/v1"] = "ambrosia/v1"
    kind: Literal["pack"] = "pack"
    metadata: PackMetadata
    actions: list[ActionDefinition] = Field(default_factory=list)


class LoadedAction(BaseModel):
    """A single action loaded from a pack, with provenance."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    version: str
    pack_id: str
    source: str  # "builtin" | "manifest" | "pack"


class LoadResult(BaseModel):
    """Result of loading a pack or manifest, including any conflicts."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str
    actions_loaded: int = 0
    action_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ContextSnapshot:
    """Read-only engagement context supplied to the matcher.

    This is the only input the matcher reads besides the registry itself and the
    policy snapshot. It must not be mutated by the matcher.
    """

    engagement_id: str
    selected_target: dict[str, object] | None = None
    scope_targets: tuple[str, ...] = field(default_factory=tuple)
    artifacts: tuple[Artifact, ...] = field(default_factory=tuple)
    inputs: dict[str, object] = field(default_factory=dict)
    available_tools: frozenset[str] = field(default_factory=frozenset)
    platform: str = "current"


@dataclass(frozen=True)
class PolicySnapshot:
    """Read-only policy view supplied to the matcher.

    Mirrors the engagement scope's security-relevant fields without exposing the
    full Scope ORM/domain object to the matcher.
    """

    allowed_effects: frozenset[str] = field(default_factory=frozenset)
    require_approval_for: frozenset[str] = field(default_factory=frozenset)
    include_hosts: tuple[str, ...] = field(default_factory=tuple)
    include_cidrs: tuple[str, ...] = field(default_factory=tuple)
    include_domains: tuple[str, ...] = field(default_factory=tuple)
    exclude_hosts: tuple[str, ...] = field(default_factory=tuple)
    exclude_cidrs: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_scope(cls, scope: Scope) -> PolicySnapshot:
        return cls(
            allowed_effects=frozenset(scope.allowed_effects),
            require_approval_for=frozenset(scope.require_approval_for),
            include_hosts=tuple(scope.include_hosts),
            include_cidrs=tuple(scope.include_cidrs),
            include_domains=tuple(scope.include_domains),
            exclude_hosts=tuple(scope.exclude_hosts),
            exclude_cidrs=tuple(scope.exclude_cidrs),
        )


__all__ = [
    "PackMetadata",
    "PackManifest",
    "LoadedAction",
    "LoadResult",
    "ContextSnapshot",
    "PolicySnapshot",
]
