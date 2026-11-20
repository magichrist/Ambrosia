"""Windows assessment pack: read-only discovery and configuration assessment.

This is the first built-in domain pack for Ambrosia. It provides bounded,
read-only network discovery and Windows service configuration observation in
explicitly authorized environments.

Safety boundary (non-negotiable): read-only discovery/configuration checks
only. This pack does not implement credential extraction/replay, hash-based
remote access, password spraying, lateral movement, unauthorized remote command
execution, persistence, stealth/evasion, destructive actions, or exfiltration.
Authentication-dependent modules are deliberately excluded and require separate
review.

Public API
----------
:func:`register_pack` — register all pack actions (with handlers) into a
:class:`~ambrosia.registry.Registry`. Registration never executes a tool or
runs an assessment; tool availability is declared as metadata only.
:func:`load_manifest` — validate and return the pack manifest without
registering anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.executors.process import ProcessExecutor
from ambrosia.registry import PackEntry, Registry
from ambrosia.registry.models import LoadResult, PackManifest

if TYPE_CHECKING:
    from ambrosia.domain.protocols import ActionHandler

from . import actions, handlers

PACK_ID = "windows-assessment"
PACK_NAME = "Windows Assessment Pack"
PACK_VERSION = "1.0.0"


# Handler classes keyed by action ID. Each is instantiated with an (optional)
# executor; when none is supplied the handler defaults to the process executor
# backed by the allowlisted nmap executable.
def _handler_class_name(action_id: str) -> str:
    return {
        "network.nmap.service_discovery": "NmapServiceDiscoveryHandler",
        "windows.smb.configuration_audit": "SmbConfigurationAuditHandler",
        "windows.ldap.domain_inventory": "LdapDomainInventoryHandler",
        "windows.http.method_observation": "HttpMethodObservationHandler",
        "windows.rdp.exposure_observation": "RdpExposureObservationHandler",
        "windows.winrm.exposure_observation": "WinrmExposureObservationHandler",
    }[action_id]


_HANDLER_CLASSES: dict[str, type[handlers.ReadOnlyToolHandler]] = {
    action.id: getattr(handlers, _handler_class_name(action.id)) for action in actions.ALL_ACTIONS
}


def _manifest_actions() -> list[dict[str, object]]:
    """Serialize action definitions for the pack manifest (no duplication)."""
    return [action.model_dump() for action in actions.ALL_ACTIONS]


PACK_MANIFEST: dict[str, object] = {
    "api_version": "ambrosia/v1",
    "kind": "pack",
    "metadata": {
        "id": PACK_ID,
        "name": PACK_NAME,
        "version": PACK_VERSION,
        "description": (
            "Read-only Windows discovery and configuration assessment pack. "
            "Discovers network services via Nmap XML and inventories SMB, "
            "LDAP, HTTP, RDP, and WinRM service configuration without "
            "modifying target state or accessing credentials."
        ),
    },
    "actions": _manifest_actions(),
}


def load_manifest() -> PackManifest:
    """Validate and return the pack manifest without registering anything.

    No tool is executed and no assessment runs as a result of calling this
    function.
    """
    return PackManifest.model_validate(PACK_MANIFEST)


def register_pack(
    registry: Registry,
    *,
    executor: ActionHandler | None = None,
) -> LoadResult:
    """Register all pack actions with their handlers into ``registry``.

    Registration is a metadata operation: it validates action definitions,
    records the pack, and associates handlers. It does not execute nmap or any
    other tool, and it does not run an assessment. Tool availability is checked
    separately by the availability matcher as a PATH/metadata check.

    ``executor`` may be supplied (typically :class:`~ambrosia.executors.fake.FakeExecutor`
    in tests) to drive execution without a real nmap installation. When omitted,
    handlers default to the process executor backed by the allowlisted nmap
    executable.
    """
    manifest = load_manifest()
    pack_id = manifest.metadata.id

    loaded_ids: list[str] = []
    # Build the default executor once; handlers use it when no test executor is
    # injected. Construction performs no tool execution.
    effective_executor: ActionHandler = executor or ProcessExecutor(executable="nmap")
    for action in manifest.actions:
        handler_cls = _HANDLER_CLASSES[action.id]
        handler = handler_cls(executor=effective_executor)
        registry.register(
            action,
            handler=handler,
            pack_id=pack_id,
            source="pack",
        )
        loaded_ids.append(action.id)

    registry._packs[pack_id] = PackEntry(  # noqa: SLF001 - pack entry bookkeeping
        manifest=manifest, enabled=True, source="pack"
    )

    return LoadResult(
        pack_id=pack_id,
        actions_loaded=len(loaded_ids),
        action_ids=list(loaded_ids),
    )


__all__ = [
    "PACK_ID",
    "PACK_NAME",
    "PACK_VERSION",
    "PACK_MANIFEST",
    "load_manifest",
    "register_pack",
    "actions",
    "handlers",
]
