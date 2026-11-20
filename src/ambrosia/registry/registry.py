"""Action registry: registration, lookup, listing, search, and pack management.

The registry stores immutable action metadata (``ActionDefinition``) and optional
executor handlers. Pack enable/disable controls whether a pack's actions are
visible to listing/search and matching. Registration never executes an action or
its handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ambrosia.domain.action import ActionDefinition
    from ambrosia.domain.protocols import ActionHandler

from ambrosia.registry.errors import (
    DuplicateActionError,
    DuplicatePackError,
    PackConflictError,
    PackNotFoundError,
)
from ambrosia.registry.models import LoadResult, PackManifest
from ambrosia.registry.validation import check_duplicate_ids, validate_action_definition


@dataclass
class PackEntry:
    """A loaded pack and its enabled state."""

    manifest: PackManifest
    enabled: bool = True
    source: str = "pack"


class Registry:
    """Central registry of action definitions and handlers.

    Actions are keyed by their namespaced ID. Packs group actions and can be
    enabled/disabled; disabled packs are excluded from listing/search/matching
    but remain registered (``get`` still works).
    """

    def __init__(self) -> None:
        self._actions: dict[str, ActionDefinition] = {}
        self._handlers: dict[str, ActionHandler] = {}
        self._action_source: dict[str, str] = {}  # action_id -> "builtin" | "manifest" | "pack"
        self._action_pack: dict[str, str | None] = {}  # action_id -> pack_id or None
        self._packs: dict[str, PackEntry] = {}

    # ------------------------------------------------------------------ register

    def register(
        self,
        definition: ActionDefinition,
        *,
        handler: ActionHandler | None = None,
        pack_id: str | None = None,
        source: str = "builtin",
    ) -> ActionDefinition:
        """Register an action definition.

        Raises :class:`DuplicateActionError` if the ID is already registered by a
        different pack/source. Validation is performed before storage. The
        handler (if any) is stored but never invoked here.
        """
        result = validate_action_definition(definition)
        if not result.ok:
            raise ValueError(
                f"invalid action definition {definition.id}: {'; '.join(result.errors)}"
            )  # noqa: TRY003

        existing_pack = self._action_pack.get(definition.id)
        if definition.id in self._actions:
            raise DuplicateActionError(  # noqa: TRY003
                f"action id {definition.id!r} already registered "
                f"(source={self._action_source.get(definition.id)}, "
                f"pack={existing_pack})"
            )

        self._actions[definition.id] = definition
        self._action_source[definition.id] = source
        self._action_pack[definition.id] = pack_id
        if handler is not None:
            self._handlers[definition.id] = handler
        return definition

    def register_builtin(
        self,
        definition: ActionDefinition,
        *,
        handler: ActionHandler | None = None,
    ) -> ActionDefinition:
        """Register a built-in action definition (no pack)."""
        return self.register(definition, handler=handler, pack_id=None, source="builtin")

    # ------------------------------------------------------------------ lookup

    def get(self, action_id: str) -> ActionDefinition | None:
        """Return the definition for an action, or ``None`` if unknown."""
        return self._actions.get(action_id)

    def get_handler(self, action_id: str) -> ActionHandler | None:
        """Return the executor handler for an action, or ``None``."""
        return self._handlers.get(action_id)

    def has(self, action_id: str) -> bool:
        return action_id in self._actions

    def action_source(self, action_id: str) -> str | None:
        return self._action_source.get(action_id)

    def action_pack_id(self, action_id: str) -> str | None:
        return self._action_pack.get(action_id)

    # ------------------------------------------------------------------ list/search/filter

    def list(
        self,
        *,
        enabled_only: bool = True,
        pack_id: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        platform: str | None = None,
    ) -> list[ActionDefinition]:
        """List registered action definitions with optional filtering.

        Filters are ANDed. When ``enabled_only`` is True (default), actions from
        disabled packs are excluded.
        """
        results: list[ActionDefinition] = []
        for definition in self._actions.values():
            pid = self._action_pack.get(definition.id)
            if enabled_only and not self._pack_enabled(pid):
                continue
            if pack_id is not None and pid != pack_id:
                continue
            if category is not None and definition.category != category:
                continue
            if tag is not None and tag not in definition.tags:
                continue
            if (
                platform is not None
                and definition.platforms
                and platform not in definition.platforms
            ):
                continue
            results.append(definition)
        results.sort(key=lambda d: (d.category, d.id))
        return results

    def search(self, query: str, *, enabled_only: bool = True) -> list[ActionDefinition]:  # type: ignore[valid-type]  # 'list' shadows builtin within this class body
        """Search actions by ID, name, description, or tags (case-insensitive)."""
        q = query.lower()
        results: list[ActionDefinition] = []
        for definition in self.list(enabled_only=enabled_only):
            haystack = " ".join(
                [
                    definition.id,
                    definition.name,
                    definition.description,
                    definition.category,
                    *definition.tags,
                ]
            ).lower()
            if q in haystack:
                results.append(definition)
        return results

    def filter(  # noqa: A002 - intentional shadow of builtin for domain language
        self,
        *,
        category: str | None = None,
        tag: str | None = None,
        platform: str | None = None,
        enabled_only: bool = True,
    ) -> list[ActionDefinition]:  # type: ignore[valid-type]  # 'list' shadows builtin within this class body
        """Alias-friendly filter by category/tag/platform."""
        return self.list(
            enabled_only=enabled_only,
            category=category,
            tag=tag,
            platform=platform,
        )

    # ------------------------------------------------------------------ packs

    def _pack_enabled(self, pack_id: str | None) -> bool:
        if pack_id is None:
            return True
        entry = self._packs.get(pack_id)
        return entry.enabled if entry is not None else True

    def enable_pack(self, pack_id: str) -> None:
        """Enable a loaded pack so its actions become visible."""
        if pack_id not in self._packs:
            raise PackNotFoundError(f"pack {pack_id!r} is not loaded")  # noqa: TRY003
        self._packs[pack_id].enabled = True

    def disable_pack(self, pack_id: str) -> None:
        """Disable a loaded pack so its actions are hidden from listing/matching."""
        if pack_id not in self._packs:
            raise PackNotFoundError(f"pack {pack_id!r} is not loaded")  # noqa: TRY003
        self._packs[pack_id].enabled = False

    def pack_enabled(self, pack_id: str) -> bool:
        entry = self._packs.get(pack_id)
        if entry is None:
            raise PackNotFoundError(f"pack {pack_id!r} is not loaded")  # noqa: TRY003
        return entry.enabled

    def list_packs(self) -> list[str]:  # type: ignore[valid-type]  # 'list' shadows builtin within this class body
        return sorted(self._packs.keys())

    def load_pack(
        self,
        manifest: PackManifest | dict[str, Any],
        *,
        source: str = "pack",
        allow_conflicts: bool = False,
    ) -> LoadResult:
        """Load a pack manifest into the registry.

        ``manifest`` may be a :class:`PackManifest` or a raw mapping (e.g. parsed
        YAML), which is validated into a :class:`PackManifest`.

        Reports duplicate action IDs and cross-pack conflicts. Unless
        ``allow_conflicts`` is set, a conflict raises :class:`PackConflictError`
        and no actions from the pack are registered.
        """
        if isinstance(manifest, dict):
            try:
                manifest = PackManifest.model_validate(manifest)
            except Exception as exc:  # pragma: no cover - pydantic raises ValidationError
                from ambrosia.registry.errors import ManifestValidationError

                raise ManifestValidationError(f"pack manifest invalid: {exc}") from exc  # noqa: TRY003
        pack_id = manifest.metadata.id
        if pack_id in self._packs:
            raise DuplicatePackError(f"pack {pack_id!r} is already loaded")  # noqa: TRY003

        definitions = manifest.actions

        # Detect duplicates within the pack first.
        internal_dups = check_duplicate_ids(definitions)
        if internal_dups:
            raise PackConflictError(  # noqa: TRY003
                f"pack {pack_id!r} contains duplicate action ids: " + "; ".join(internal_dups)
            )

        # Detect conflicts with already-registered actions.
        conflicts: list[str] = []
        for definition in definitions:
            existing_pack = self._action_pack.get(definition.id)
            if definition.id in self._actions and existing_pack != pack_id:
                conflicts.append(
                    f"action {definition.id!r} already registered by pack {existing_pack!r}"
                )

        result = LoadResult(pack_id=pack_id)
        if conflicts and not allow_conflicts:
            result.errors = [f"pack {pack_id!r} conflicts: " + "; ".join(conflicts)]
            raise PackConflictError(result.errors[0])  # noqa: TRY003

        if conflicts:
            result.warnings.append(
                f"pack {pack_id!r} overrides existing actions: " + "; ".join(conflicts)
            )

        for definition in definitions:
            try:
                self.register(
                    definition,
                    pack_id=pack_id,
                    source=source,
                )
                result.actions_loaded += 1
                result.action_ids.append(definition.id)
            except DuplicateActionError as exc:
                # Should not happen given the pre-check above; record defensively.
                result.errors.append(str(exc))

        self._packs[pack_id] = PackEntry(manifest=manifest, enabled=True, source=source)
        return result

    def unload_pack(self, pack_id: str) -> list[str]:  # type: ignore[valid-type]  # 'list' shadows builtin within this class body
        """Unload a pack and remove its actions from the registry.

        Returns the list of removed action IDs.
        """
        if pack_id not in self._packs:
            raise PackNotFoundError(f"pack {pack_id!r} is not loaded")  # noqa: TRY003
        entry = self._packs.pop(pack_id)
        removed: list[str] = []
        for action_id in [a.id for a in entry.manifest.actions]:
            if self._action_pack.get(action_id) == pack_id:
                self._actions.pop(action_id, None)
                self._handlers.pop(action_id, None)
                self._action_source.pop(action_id, None)
                self._action_pack.pop(action_id, None)
                removed.append(action_id)
        return removed


__all__ = [
    "PackEntry",
    "Registry",
]
