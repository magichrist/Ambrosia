"""Deterministic argv builders for authorized red-team tool wrappers.

Every builder returns a ``list[str]`` passed to the shell-free
:class:`~ambrosia.executors.process.ProcessExecutor`. Inputs are validated at
runtime; no value is interpolated into a shell string. The reserved
``authorization_reference`` input is never forwarded to a tool.
"""

from __future__ import annotations

_SUPPORTED_TARGET_SCHEMES = ("smb", "ldap", "http")


def _require_str(inputs: dict[str, object], key: str) -> str:
    value = inputs.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"authorized operation requires a non-empty {key!r} string"
        raise ValueError(msg)
    return value.strip()


def _optional_str(inputs: dict[str, object], key: str) -> str | None:
    value = inputs.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{key!r} must be a string"
        raise TypeError(msg)
    return value.strip() or None


def _extra_args(inputs: dict[str, object]) -> list[str]:
    value = inputs.get("extra_args", [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = "'extra_args' must be a list of strings"
        raise ValueError(msg)
    return list(value)


def _netexec_credentials(inputs: dict[str, object]) -> list[str]:
    flags: list[str] = []
    username = _optional_str(inputs, "username")
    password = _optional_str(inputs, "password")
    if username:
        flags.extend(["-u", username])
    if password:
        flags.extend(["-p", password])
    if not username and not password and inputs.get("no_pass", False):
        flags.append("-no-pass")
    return flags


def _impacket_target(inputs: dict[str, object], target: str) -> str:
    """Build impacket's ``[[domain/]user[:pass]@]target`` token."""
    username = _optional_str(inputs, "username")
    password = _optional_str(inputs, "password")
    domain = _optional_str(inputs, "domain")
    if not username:
        return target
    principal = f"{domain}/{username}" if domain else username
    if password:
        principal = f"{principal}:{password}"
    return f"{principal}@{target}"


def build_secretsdump_argv(inputs: dict[str, object]) -> list[str]:
    """Impacket ``secretsdump.py`` — SAM/NTDS credential extraction."""
    target = _require_str(inputs, "target")
    argv: list[str] = []
    if inputs.get("no_pass", True):
        argv.append("-no-pass")
    argv.extend(_netexec_credentials(inputs))
    argv.extend(_extra_args(inputs))
    argv.append(target)
    return argv


def build_samdump2_argv(inputs: dict[str, object]) -> list[str]:
    """Offline ``samdump2`` over an authorized SYSTEM/SAM hive pair."""
    return [_require_str(inputs, "system_hive"), _require_str(inputs, "sam_hive")]


def build_netexec_argv(inputs: dict[str, object]) -> list[str]:
    """NetExec (``netexec``/``nxc``) SMB authentication and enumeration."""
    protocol = _require_str(inputs, "protocol").lower()
    if protocol not in _SUPPORTED_TARGET_SCHEMES:
        msg = f"unsupported NetExec protocol: {protocol!r}"
        raise ValueError(msg)
    return [
        protocol,
        _require_str(inputs, "target"),
        *_netexec_credentials(inputs),
        *_extra_args(inputs),
    ]


def build_netexec_exec_argv(inputs: dict[str, object]) -> list[str]:
    """NetExec SMB remote command execution (psexec-style via ``-x``)."""
    command = _require_str(inputs, "command")
    return [
        "smb",
        _require_str(inputs, "target"),
        *_netexec_credentials(inputs),
        "-x",
        command,
        *_extra_args(inputs),
    ]


def build_psexec_argv(inputs: dict[str, object]) -> list[str]:
    """Impacket ``psexec.py`` remote command execution."""
    target = _impacket_target(inputs, _require_str(inputs, "target"))
    return [target, _require_str(inputs, "command"), *_extra_args(inputs)]


def build_domain_enumeration_argv(inputs: dict[str, object]) -> list[str]:
    """Impacket ``GetADUsers.py`` Active Directory user enumeration."""
    target = _impacket_target(inputs, _require_str(inputs, "target"))
    argv = [target]
    domain = _optional_str(inputs, "domain")
    if domain:
        argv.extend(["-all", domain])
    argv.extend(_extra_args(inputs))
    return argv


def build_ntlm_relay_argv(inputs: dict[str, object]) -> list[str]:
    """Impacket ``ntlmrelayx.py`` NTLM relay against an SMB target."""
    target = _require_str(inputs, "target")
    return [
        "-t",
        f"smb://{target}",
        "-smb2support",
        *_extra_args(inputs),
    ]


__all__ = [
    "build_domain_enumeration_argv",
    "build_netexec_argv",
    "build_netexec_exec_argv",
    "build_ntlm_relay_argv",
    "build_psexec_argv",
    "build_samdump2_argv",
    "build_secretsdump_argv",
]
