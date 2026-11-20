"""Opt-in authorized operations pack (high-impact red-team tool wrappers).

This pack wraps installed Windows/Active Directory assessment binaries
(Impacket, NetExec, samdump2) through the shell-free argv executor. It is
**never** registered by ``build_registry()`` or the default service startup.
An operator must explicitly call :func:`register_authorized_operations`, widen
the engagement scope to allow the effects, supply an authorization reference,
and (for remote-changing actions) grant approval.

No tool is installed, downloaded, or executed by importing or registering this
pack. Tool availability is declared as metadata and checked as a PATH lookup by
the availability matcher.

See ``docs/authorized-operations.md`` for the safety case.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.executors.process import ProcessExecutor
from ambrosia.registry import PackEntry, Registry
from ambrosia.registry.models import LoadResult, PackManifest

from . import actions, argv, handlers

if TYPE_CHECKING:
    from ambrosia.domain.protocols import ActionHandler

PACK_ID = "authorized-operations"
PACK_NAME = "Authorized Operations Pack"
PACK_VERSION = "1.0.0"

PACK_MANIFEST: dict[str, object] = {
    "api_version": "ambrosia/v1",
    "kind": "pack",
    "metadata": {
        "id": PACK_ID,
        "name": PACK_NAME,
        "version": PACK_VERSION,
        "description": (
            "Opt-in wrappers for installed Impacket, NetExec, and samdump2 tools. "
            "High-impact: requires explicit authorization, effect allowlisting, "
            "and approval for remote-changing actions."
        ),
    },
    "actions": [definition.model_dump() for definition in actions.ALL_ACTIONS],
}


def load_manifest() -> PackManifest:
    """Validate and return the pack manifest without registering anything."""
    return PackManifest.model_validate(PACK_MANIFEST)


def register_authorized_operations(
    registry: Registry,
    *,
    executor: ActionHandler | None = None,
) -> LoadResult:
    """Explicitly register the high-impact pack into ``registry``.

    This function is deliberately not called from production startup. The
    caller is asserting that the engagement is authorized for these effects.
    """
    manifest = load_manifest()
    loaded_ids: list[str] = []
    for definition in manifest.actions:
        # Each action declares its own allowlisted executable. The argv builder
        # emits only arguments; the executor prepends the fixed executable.
        tool_executor: ActionHandler = executor or ProcessExecutor(
            executable=definition.executor.executable or definition.id
        )
        registry.register(
            definition,
            handler=handlers.AuthorizedToolHandler(tool_executor, definition),
            pack_id=PACK_ID,
            source="pack",
        )
        loaded_ids.append(definition.id)

    registry._packs[PACK_ID] = PackEntry(  # noqa: SLF001 - pack bookkeeping
        manifest=manifest, enabled=True, source="pack"
    )
    return LoadResult(
        pack_id=PACK_ID,
        actions_loaded=len(loaded_ids),
        action_ids=loaded_ids,
        warnings=[
            "High-impact pack: every run requires an explicit authorization "
            "reference and effect allowlisting."
        ],
    )


__all__ = [
    "PACK_ID",
    "PACK_NAME",
    "PACK_VERSION",
    "PACK_MANIFEST",
    "actions",
    "argv",
    "handlers",
    "load_manifest",
    "register_authorized_operations",
]
