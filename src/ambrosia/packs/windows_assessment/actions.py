"""Action definitions for the Windows assessment pack.

Every action is read-only: bounded discovery and configuration observation.
None of them modify target state, extract or replay credentials, perform
password spraying, lateral movement, persistence, evasion, or remote command
execution.

Action IDs follow the namespaced dotted form required by the registry
(see :mod:`ambrosia.registry.validation`). Declared effects are limited to
``network_observe`` and ``local_read``, the effect classes permitted in the
initial built-in pack (docs/00_MASTER_PLAN.md 10.2).
"""

from __future__ import annotations

from typing import Literal

from ambrosia.domain.action import (
    ActionDefinition,
    ArtifactRequirement,
    ExecutorReference,
    ToolDependency,
)

_Risk = Literal["info", "low", "moderate", "high", "critical"]

_NMAP_DEPENDENCY = ToolDependency(
    name="nmap",
    version="7.90",
    # Metadata-only declaration. The registry never executes this command at
    # registration or import time; availability is a PATH check performed by
    # the matcher (see docs/01_SHARED_CONTRACTS.md 8.6).
    check_command=["nmap", "--version"],
)

_NMAP_EXECUTOR = ExecutorReference(kind="process", executable="nmap")

_SCOPE_FIELD_TARGET = ["target"]

# Nmap reports service names from its own service-probe fingerprint database,
# which differ from the canonical Windows service labels used in action IDs.
# Follow-up prerequisites accept BOTH forms so they work on real scans as well
# as on hand-authored artifacts. The matcher treats a collection in ``where``
# as "any of these values" (see registry/matcher.py::_predicate_matches).
_NMAP_SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "smb": ("smb", "microsoft-ds"),
    "ldap": ("ldap", "ldaps"),
    "http": ("http", "https", "www", "http-alt"),
    "rdp": ("rdp", "ms-wbt-server"),
    "winrm": ("winrm", "wsman", "wsman-http"),
}


def _service_where(canonical: str) -> dict[str, object]:
    """Build a ``where`` predicate accepting canonical and real Nmap names."""
    return {"service_name": list(_NMAP_SERVICE_ALIASES[canonical])}


def _discovery_action(
    *,
    action_id: str,
    name: str,
    description: str,
    category: str,
    tags: list[str],
    required_artifacts: list[ArtifactRequirement],
    output_artifact_types: list[str],
    risk: _Risk,
    input_properties: dict[str, object],
    input_required: list[str],
) -> ActionDefinition:
    return ActionDefinition(
        id=action_id,
        version="1.0.0",
        name=name,
        description=description,
        category=category,
        tags=tags,
        platforms=["linux", "windows", "darwin"],
        phase_refs=["windows.discovery"],
        required_artifacts=required_artifacts,
        input_schema={
            "type": "object",
            "properties": input_properties,
            "required": input_required,
            "additionalProperties": False,
        },
        output_artifact_types=output_artifact_types,
        executor=_NMAP_EXECUTOR,
        dependencies=[_NMAP_DEPENDENCY],
        effects=["network_observe"],
        risk=risk,
        scope_fields=_SCOPE_FIELD_TARGET,
        approval_required=False,
        timeout_seconds=120,
        max_output_bytes=2_000_000,
        parser_refs=["nmap_xml"],
    )


# ---------------------------------------------------------------------------
# network.nmap.service_discovery
# ---------------------------------------------------------------------------

NETWORK_NMAP_SERVICE_DISCOVERY = _discovery_action(
    action_id="network.nmap.service_discovery",
    name="Network Service Discovery (Nmap)",
    description=(
        "Bounded, read-only network service discovery using Nmap XML output. "
        "Scans only the declared ports on an explicitly in-scope target and "
        "produces typed ``network.service`` artifacts from structured XML -- "
        "never from human-readable tables. Service names are recorded as "
        "observed (for example ``microsoft-ds`` rather than ``smb``); follow-up "
        "actions accept both the real Nmap name and the canonical label."
    ),
    category="discovery",
    tags=["discovery", "network", "nmap", "read-only"],
    required_artifacts=[],
    output_artifact_types=["network.service"],
    risk="low",
    input_properties={
        "target": {
            "type": "string",
            "description": "Target host or IP address to discover services on.",
        },
        "ports": {
            "type": "string",
            "description": "Comma-separated port list to scan (bounded).",
            "default": "80,443,445,3389,5985",
        },
    },
    input_required=["target"],
)

# ---------------------------------------------------------------------------
# windows.smb.configuration_audit
# ---------------------------------------------------------------------------

WINDOWS_SMB_CONFIGURATION_AUDIT = _discovery_action(
    action_id="windows.smb.configuration_audit",
    name="SMB Service Configuration Audit",
    description=(
        "Read-only SMB service identification and configuration inventory. "
        "Requires a discovered SMB service on the same target. Uses Nmap SMB "
        "NSE scripts (smb-protocols, smb-os-discovery, smb-security-mode) to "
        "inventory protocol versions, domain, forest, and server role. Produces "
        "``windows.domain`` and ``windows.host_role`` artifacts plus "
        "observations. Never extracts credentials or modifies SMB settings."
    ),
    category="configuration",
    tags=["windows", "smb", "inventory", "read-only"],
    required_artifacts=[
        ArtifactRequirement(
            type="network.service",
            where=_service_where("smb"),
            same_target=True,
        )
    ],
    output_artifact_types=["windows.domain", "windows.host_role", "observation"],
    risk="low",
    input_properties={
        "target": {
            "type": "string",
            "description": "Target host or IP address running the SMB service.",
        },
        "port": {
            "type": "integer",
            "description": "SMB port.",
            "default": 445,
            "minimum": 1,
            "maximum": 65535,
        },
    },
    input_required=["target"],
)

# ---------------------------------------------------------------------------
# windows.ldap.domain_inventory
# ---------------------------------------------------------------------------

WINDOWS_LDAP_DOMAIN_INVENTORY = _discovery_action(
    action_id="windows.ldap.domain_inventory",
    name="LDAP Service / Domain Inventory",
    description=(
        "Read-only LDAP service and domain inventory. Requires a discovered "
        "LDAP service on the same target. Observes LDAP service metadata from "
        "Nmap's service fingerprint. Any domain name is a best-effort heuristic "
        "inferred from the target's hostname (no Nmap script is run and no "
        "authoritative directory query is made); forest is not enumerated. "
        "Produces ``windows.domain`` artifacts and observations. Never performs "
        "authentication, binding, or credential access."
    ),
    category="configuration",
    tags=["windows", "ldap", "inventory", "read-only", "domain"],
    required_artifacts=[
        ArtifactRequirement(
            type="network.service",
            where=_service_where("ldap"),
            same_target=True,
        )
    ],
    output_artifact_types=["windows.domain", "observation"],
    risk="low",
    input_properties={
        "target": {
            "type": "string",
            "description": "Target host or IP address running the LDAP service.",
        },
        "port": {
            "type": "integer",
            "description": "LDAP port.",
            "default": 389,
            "minimum": 1,
            "maximum": 65535,
        },
    },
    input_required=["target"],
)

# ---------------------------------------------------------------------------
# windows.http.method_observation
# ---------------------------------------------------------------------------

WINDOWS_HTTP_METHOD_OBSERVATION = _discovery_action(
    action_id="windows.http.method_observation",
    name="HTTP Method / Configuration Observation",
    description=(
        "Non-mutating observation of advertised HTTP methods and configuration. "
        "Requires a discovered HTTP service on the same target. Uses the Nmap "
        "http-methods script to enumerate advertised methods. Advertised "
        "methods are observations only and do not prove exploitability. "
        "Never performs upload, injection, or mutation testing."
    ),
    category="observation",
    tags=["windows", "http", "observation", "read-only"],
    required_artifacts=[
        ArtifactRequirement(
            type="network.service",
            where=_service_where("http"),
            same_target=True,
        )
    ],
    output_artifact_types=["observation"],
    risk="info",
    input_properties={
        "target": {
            "type": "string",
            "description": "Target host or IP address running the HTTP service.",
        },
        "port": {
            "type": "integer",
            "description": "HTTP port.",
            "default": 80,
            "minimum": 1,
            "maximum": 65535,
        },
    },
    input_required=["target"],
)

# ---------------------------------------------------------------------------
# windows.rdp.exposure_observation
# ---------------------------------------------------------------------------

WINDOWS_RDP_EXPOSURE_OBSERVATION = _discovery_action(
    action_id="windows.rdp.exposure_observation",
    name="RDP Exposure / Configuration Observation",
    description=(
        "Read-only observation of RDP exposure and configuration. Requires a "
        "discovered RDP service on the same target. Reports the RDP security "
        "layer and encryption level observed by Nmap scripts. Never performs "
        "authentication, credential replay, or remote command execution."
    ),
    category="observation",
    tags=["windows", "rdp", "observation", "read-only"],
    required_artifacts=[
        ArtifactRequirement(
            type="network.service",
            where=_service_where("rdp"),
            same_target=True,
        )
    ],
    output_artifact_types=["observation"],
    risk="info",
    input_properties={
        "target": {
            "type": "string",
            "description": "Target host or IP address running the RDP service.",
        },
        "port": {
            "type": "integer",
            "description": "RDP port.",
            "default": 3389,
            "minimum": 1,
            "maximum": 65535,
        },
    },
    input_required=["target"],
)

# ---------------------------------------------------------------------------
# windows.winrm.exposure_observation
# ---------------------------------------------------------------------------

WINDOWS_WINRM_EXPOSURE_OBSERVATION = _discovery_action(
    action_id="windows.winrm.exposure_observation",
    name="WinRM Exposure / Configuration Observation",
    description=(
        "Read-only observation of WinRM exposure and configuration. Requires a "
        "discovered WinRM service on the same target. Reports WinRM "
        "authentication and transport settings observed by Nmap scripts. Never "
        "performs authentication, credential replay, or remote command "
        "execution."
    ),
    category="observation",
    tags=["windows", "winrm", "observation", "read-only"],
    required_artifacts=[
        ArtifactRequirement(
            type="network.service",
            where=_service_where("winrm"),
            same_target=True,
        )
    ],
    output_artifact_types=["observation"],
    risk="info",
    input_properties={
        "target": {
            "type": "string",
            "description": "Target host or IP address running the WinRM service.",
        },
        "port": {
            "type": "integer",
            "description": "WinRM port.",
            "default": 5985,
            "minimum": 1,
            "maximum": 65535,
        },
    },
    input_required=["target"],
)

# ---------------------------------------------------------------------------
# Pack action registry
# ---------------------------------------------------------------------------

ALL_ACTIONS: list[ActionDefinition] = [
    NETWORK_NMAP_SERVICE_DISCOVERY,
    WINDOWS_SMB_CONFIGURATION_AUDIT,
    WINDOWS_LDAP_DOMAIN_INVENTORY,
    WINDOWS_HTTP_METHOD_OBSERVATION,
    WINDOWS_RDP_EXPOSURE_OBSERVATION,
    WINDOWS_WINRM_EXPOSURE_OBSERVATION,
]

ACTIONS_BY_ID: dict[str, ActionDefinition] = {action.id: action for action in ALL_ACTIONS}

__all__ = [
    "NETWORK_NMAP_SERVICE_DISCOVERY",
    "WINDOWS_SMB_CONFIGURATION_AUDIT",
    "WINDOWS_LDAP_DOMAIN_INVENTORY",
    "WINDOWS_HTTP_METHOD_OBSERVATION",
    "WINDOWS_RDP_EXPOSURE_OBSERVATION",
    "WINDOWS_WINRM_EXPOSURE_OBSERVATION",
    "ALL_ACTIONS",
    "ACTIONS_BY_ID",
]
