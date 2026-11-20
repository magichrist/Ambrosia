"""Action definitions for the opt-in authorized operations pack.

These operations are high-impact: credential access, remote state change, and
authentication. They are NOT registered by the default registry. Registration
requires an explicit call to ``register_authorized_operations`` and every run
requires an explicit authorization reference (see ``authorization.py``).

Tool names are declared as metadata only. Nothing here installs, downloads, or
executes a tool; availability is a PATH check performed by the matcher.
"""

from __future__ import annotations

from typing import Any

from ambrosia.domain.action import ActionDefinition, ExecutorReference, ToolDependency


def _dependency(name: str) -> list[ToolDependency]:
    """Metadata-only declaration; never executed during registration."""
    return [ToolDependency(name=name, check_command=[name, "--help"])]


def _definition(
    *,
    action_id: str,
    name: str,
    description: str,
    executable: str,
    properties: dict[str, Any],
    required: list[str],
    effects: list[str],
    scope_fields: list[str],
    risk: str,
) -> ActionDefinition:
    return ActionDefinition(
        id=action_id,
        version="1.0.0",
        name=name,
        description=description,
        category="authorized-operations",
        tags=["windows", "active-directory", "authorized", "red-team"],
        platforms=["linux", "darwin", "windows"],
        phase_refs=["windows.authorized-operations"],
        required_artifacts=[],
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        output_artifact_types=[],
        executor=ExecutorReference(kind="process", executable=executable),
        dependencies=_dependency(executable),
        effects=effects,
        risk=risk,  # type: ignore[arg-type]
        scope_fields=scope_fields,
        approval_required=True,
        timeout_seconds=300,
        max_output_bytes=2_000_000,
        parser_refs=[],
    )


_TARGET = {"type": "string", "description": "In-scope target address or hostname."}
_USERNAME = {"type": "string", "description": "Account used for the authorized check."}
_PASSWORD = {"type": "string", "description": "Credential for the authorized account."}
_DOMAIN = {"type": "string", "description": "Optional AD domain."}
_EXTRA = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Additional tool flags, passed as separate argv values.",
}
_COMMAND = {"type": "string", "description": "Command to execute on the authorized target."}
_SHOW_OUTPUT = {
    "type": "boolean",
    "description": (
        "Emit raw tool output as an execution event. Raw output is persisted in "
        "execution history and may contain credential material; off by default."
    ),
}
_AUTH = {
    "type": "string",
    "description": "Explicit per-run authorization reference (rules-of-engagement id).",
}


def _properties(**extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorization_reference": _AUTH,
        "show_output": _SHOW_OUTPUT,
        "extra_args": _EXTRA,
        **extra,
    }


SECRETSDUMP = _definition(
    action_id="windows.credentials.secretsdump",
    name="Impacket secretsdump (authorized)",
    description=(
        "Extract SAM/NTDS credential material from an explicitly in-scope host "
        "using an installed Impacket secretsdump.py. Requires an authorization reference."
    ),
    executable="secretsdump.py",
    properties=_properties(
        target=_TARGET,
        username=_USERNAME,
        password=_PASSWORD,
        no_pass={"type": "boolean", "description": "Use a null session attempt."},
    ),
    required=["target", "authorization_reference"],
    effects=["credential_access"],
    scope_fields=["target"],
    risk="critical",
)

SAMDUMP2 = _definition(
    action_id="windows.credentials.samdump2",
    name="samdump2 offline hive extraction (authorized)",
    description=(
        "Extract hashes from previously acquired SYSTEM/SAM hives using an installed "
        "samdump2 binary. Offline action; still requires an authorization reference."
    ),
    executable="samdump2",
    properties=_properties(
        system_hive={"type": "string", "description": "Path to an acquired SYSTEM hive."},
        sam_hive={"type": "string", "description": "Path to an acquired SAM hive."},
    ),
    required=["system_hive", "sam_hive", "authorization_reference"],
    effects=["credential_access"],
    scope_fields=[],
    risk="critical",
)

NETEXEC = _definition(
    action_id="windows.smb.netexec",
    name="NetExec SMB enumeration (authorized)",
    description=(
        "Authenticate and enumerate an in-scope SMB host with an installed NetExec "
        "(netexec/nxc) binary. Requires an authorization reference."
    ),
    executable="netexec",
    properties=_properties(
        target=_TARGET,
        protocol={"type": "string", "description": "smb, ldap, or http.", "default": "smb"},
        username=_USERNAME,
        password=_PASSWORD,
        no_pass={"type": "boolean", "description": "Attempt a null session."},
    ),
    required=["target", "authorization_reference"],
    effects=["authentication", "remote_read"],
    scope_fields=["target"],
    risk="high",
)

NETEXEC_EXEC = _definition(
    action_id="windows.lateral.netexec_exec",
    name="NetExec remote execution (authorized)",
    description=(
        "Execute a command on an in-scope host with NetExec's -x flag. Remote state "
        "changing; requires an authorization reference and approval."
    ),
    executable="netexec",
    properties=_properties(
        target=_TARGET,
        username=_USERNAME,
        password=_PASSWORD,
        command=_COMMAND,
    ),
    required=["target", "command", "authorization_reference"],
    effects=["remote_change"],
    scope_fields=["target"],
    risk="critical",
)

PSEXEC = _definition(
    action_id="windows.lateral.psexec",
    name="Impacket psexec (authorized)",
    description=(
        "Run a command on an in-scope host with an installed Impacket psexec.py. "
        "Remote state changing; requires an authorization reference and approval."
    ),
    executable="psexec.py",
    properties=_properties(
        target=_TARGET,
        username=_USERNAME,
        password=_PASSWORD,
        domain=_DOMAIN,
        command=_COMMAND,
    ),
    required=["target", "command", "authorization_reference"],
    effects=["remote_change"],
    scope_fields=["target"],
    risk="critical",
)

DOMAIN_ENUM = _definition(
    action_id="windows.ad.domain_enumeration",
    name="Active Directory user enumeration (authorized)",
    description=(
        "Enumerate AD users with an installed Impacket GetADUsers.py against an "
        "in-scope domain controller. Requires an authorization reference."
    ),
    executable="GetADUsers.py",
    properties=_properties(
        target=_TARGET,
        username=_USERNAME,
        password=_PASSWORD,
        domain=_DOMAIN,
    ),
    required=["target", "authorization_reference"],
    effects=["authentication", "remote_read"],
    scope_fields=["target"],
    risk="high",
)

NTLM_RELAY = _definition(
    action_id="windows.smb.ntlm_relay",
    name="NTLM-to-SMB relay (authorized)",
    description=(
        "Relay captured NTLM authentication to an in-scope SMB target with an "
        "installed Impacket ntlmrelayx.py. Requires an authorization reference and approval."
    ),
    executable="ntlmrelayx.py",
    properties=_properties(target=_TARGET),
    required=["target", "authorization_reference"],
    effects=["credential_access", "remote_change"],
    scope_fields=["target"],
    risk="critical",
)

ALL_ACTIONS: tuple[ActionDefinition, ...] = (
    SECRETSDUMP,
    SAMDUMP2,
    NETEXEC,
    NETEXEC_EXEC,
    PSEXEC,
    DOMAIN_ENUM,
    NTLM_RELAY,
)

__all__ = ["ALL_ACTIONS"]
