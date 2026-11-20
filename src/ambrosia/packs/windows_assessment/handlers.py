"""Action handlers for the Windows assessment pack.

Handlers implement the :class:`ambrosia.domain.protocols.ActionHandler`
protocol. Each handler runs its tool through an injected executor
(:class:`ambrosia.executors.process.ProcessExecutor` in production, a fake or
stub in tests), parses structured tool output with the matching adapter, and
emits :class:`ambrosia.domain.protocols.ExecutionEvent` instances including
:class:`ArtifactProducedEvent`s that carry typed artifact drafts.

Handlers are read-only: they never modify target state, never extract or
replay credentials, never perform password spraying or lateral movement, and
never execute remote commands. Tool availability and version are declared as
metadata (see :mod:`ambrosia.packs.windows_assessment.actions`) and are never
executed during pack registration or import.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionHandler,
    ActionRequest,
    ExecutionEvent,
)
from ambrosia.executors.adapters import NmapAdapter, NmapParseResult, ToolAdapter
from ambrosia.executors.process import ProcessExecutor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Common HTTP methods that Nmap's http-methods script may advertise. Parsing is
# conservative: only well-known method tokens are recognized, and the result is
# treated strictly as an observation -- advertised methods do not prove
# exploitability (see docs/limitations.md).
_HTTP_METHOD_RE = re.compile(
    r"\b(GET|HEAD|POST|PUT|DELETE|PATCH|OPTIONS|TRACE|CONNECT)\b",
    re.IGNORECASE,
)

# Well-known roles observed from SMB/OS fingerprinting.
_DOMAIN_CONTROLLER_HINTS = ("domain controller", "dc", "active directory")


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _extract_domain_from_scripts(scripts: dict[str, str]) -> tuple[str | None, str | None]:
    """Extract domain/forest from Nmap SMB/LDAP script output.

    Script output is free-form text embedded inside structured Nmap XML. It may
    arrive as a single normalized line (XML attribute value normalization) or
    across multiple lines, so extraction uses a regex over the whole output
    rather than line anchors. Only well-known ``key: value`` pairs are
    recognized; anything else is ignored rather than guessed.
    """
    domain: str | None = None
    forest: str | None = None
    for output in scripts.values():
        if domain is None:
            match = re.search(r"domain name:\s*(\S+)", output, re.IGNORECASE)
            if match:
                domain = match.group(1)
        if forest is None:
            match = re.search(r"forest name:\s*(\S+)", output, re.IGNORECASE)
            if match:
                forest = match.group(1)
    return domain, forest


def _extract_domain_from_hostname(hostnames: list[str]) -> str | None:
    """Best-effort domain guess from a fully-qualified hostname.

    ``dc01.corp.local`` -> ``corp.local``. This is a heuristic, not authoritative
    directory data; it is documented as a limitation.
    """
    for name in hostnames:
        if "." in name:
            return name.split(".", 1)[1]
    return None


def _is_domain_controller(os_matches: list[str], product: str | None) -> bool:
    haystack = " ".join([*os_matches, product or ""]).lower()
    return any(hint in haystack for hint in _DOMAIN_CONTROLLER_HINTS)


class ReadOnlyToolHandler(ActionHandler, ABC):
    """Base handler for read-only tool actions.

    Subclasses implement :meth:`_build_inputs` (to resolve action inputs into
    adapter inputs) and :meth:`_drafts_from_result` (to convert parsed tool
    output into artifact drafts).
    """

    def __init__(
        self,
        executor: ActionHandler,
        adapter: ToolAdapter | None = None,
        *,
        action_id: str = "",
    ) -> None:
        self._executor = executor
        # Concrete handlers always supply an adapter; typed here as ToolAdapter
        # so subclasses can call build_argv without an optional check.
        self._adapter: ToolAdapter = adapter  # type: ignore[assignment]
        self._action_id = action_id

    # ------------------------------------------------------------------ execute

    async def execute(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run the adapter through the executor and emit artifact draft events."""
        execution_id = request.execution_id
        yield ExecutionEvent(
            kind="ProgressEvent",
            execution_id=execution_id,
            payload={"message": f"starting {self._action_id}", "action": self._action_id},
        )

        try:
            stdout = await self._capture_stdout(request, context, execution_id)
            result = cast("NmapParseResult", self._adapter.parse_output(stdout))
            # Draft construction validates and converts tool output into typed
            # artifact values; keep it inside the guard so a parsing error is
            # reported as a FailedEvent rather than escaping the generator.
            drafts = list(self._drafts_from_result(result, request, context, execution_id))
        except Exception as exc:  # noqa: BLE001 - translate to a typed failed event
            yield ExecutionEvent(
                kind="FailedEvent",
                execution_id=execution_id,
                payload={
                    "code": "execution_error",
                    "message": f"{self._action_id} failed: {exc}",
                    "retryable": False,
                },
            )
            return

        for draft in drafts:
            yield ExecutionEvent(
                kind="ArtifactProducedEvent",
                execution_id=execution_id,
                payload=draft,
            )
        yield ExecutionEvent(
            kind="CompletedEvent",
            execution_id=execution_id,
            payload={
                "summary": {
                    "artifacts_produced": len(drafts),
                    "adapter": self._adapter.name,
                    "action": self._action_id,
                }
            },
        )

    # ------------------------------------------------------------------ internals

    async def _capture_stdout(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> str:
        """Run the adapter through the executor and return combined stdout.

        Only streamed ``OutputChunkEvent`` text is captured; completed-event
        summaries are not concatenated to avoid double counting executors that
        both stream and summarize (such as the process executor).
        """
        inputs = self._build_inputs(request)
        argv = self._adapter.build_argv(**inputs)
        exec_request = ActionRequest(
            execution_id=execution_id,
            action_id=self._action_id,
            inputs={"argv": argv},
        )
        chunks: list[str] = []
        async for event in self._executor.execute(exec_request, context):
            if event.kind == "OutputChunkEvent":
                chunks.append(str(event.payload.get("text", "")))
        return "".join(chunks)

    @abstractmethod
    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        """Return adapter inputs resolved from the validated action inputs."""

    @abstractmethod
    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        """Convert parsed tool output into artifact drafts."""

    def _observation_draft(
        self,
        *,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
        target_ref: str,
        title: str,
        description: str | None,
        evidence: dict[str, object],
        source_artifact_id: str | None = None,
        severity: str = "info",
        confidence: float = 0.8,
        remediation: str | None = None,
    ) -> dict[str, object]:
        """Build an ``observation`` artifact draft (never a finding)."""
        value: dict[str, object] = {
            "id": str(uuid4()),
            "engagement_id": context.engagement_id,
            "target_ref": target_ref,
            "source_artifact_id": source_artifact_id,
            "title": title,
            "description": description,
            "evidence": evidence,
            "impact": None,
            "remediation": remediation,
            "severity": severity,
            "confidence": confidence,
        }
        return {
            "type": "observation",
            "value": value,
            "target_ref": target_ref,
            "source_id": self._action_id,
            "source_execution_id": execution_id,
            "confidence": confidence,
            "sensitivity": "internal",
            "metadata": {"parser": "nmap_xml", "kind": "observation"},
        }


# ---------------------------------------------------------------------------
# network.nmap.service_discovery
# ---------------------------------------------------------------------------


class NmapServiceDiscoveryHandler(ReadOnlyToolHandler):
    """Discovers network services on a bounded target/port list via Nmap XML."""

    def __init__(
        self, executor: ActionHandler | None = None, adapter: ToolAdapter | None = None
    ) -> None:
        super().__init__(
            executor or ProcessExecutor(executable="nmap"),
            adapter or NmapAdapter(),
            action_id="network.nmap.service_discovery",
        )

    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        return {
            "target": str(request.inputs.get("target", "")),
            "ports": str(request.inputs.get("ports", "80,443,445,3389,5985")),
        }

    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        drafts: list[dict[str, object]] = []
        target = str(request.inputs.get("target", ""))
        for service in result.open_services:
            drafts.append(
                {
                    "type": "network.service",
                    "value": {
                        "host_ref": service.host,
                        "port": service.port,
                        "protocol": service.protocol,
                        "service_name": service.service_name,
                        "product": service.product,
                        "version": service.version,
                        "state": service.state,
                    },
                    "target_ref": service.host or target,
                    "source_id": self._action_id,
                    "source_execution_id": execution_id,
                    "confidence": 0.85,
                    "sensitivity": "internal",
                    "metadata": {
                        "parser": "nmap_xml",
                        "host": service.host,
                        "port": service.port,
                    },
                }
            )
        return drafts


# ---------------------------------------------------------------------------
# windows.smb.configuration_audit
# ---------------------------------------------------------------------------


class SmbConfigurationAuditHandler(ReadOnlyToolHandler):
    """Read-only SMB configuration inventory via Nmap SMB scripts."""

    def __init__(
        self, executor: ActionHandler | None = None, adapter: ToolAdapter | None = None
    ) -> None:
        super().__init__(
            executor or ProcessExecutor(executable="nmap"),
            adapter or NmapAdapter(),
            action_id="windows.smb.configuration_audit",
        )

    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        port = int(str(request.inputs.get("port", 445)))
        return {
            "target": str(request.inputs.get("target", "")),
            "ports": str(port),
            "scripts": "smb-protocols,smb-os-discovery,smb-security-mode",
        }

    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        drafts: list[dict[str, object]] = []
        target = str(request.inputs.get("target", ""))
        port = int(str(request.inputs.get("port", 445)))
        for host in result.hosts:
            for service in host.services:
                if service.state != "open" or service.port != port:
                    continue
                target_ref = service.host or target
                domain, forest = _extract_domain_from_scripts(service.scripts)
                if domain is None:
                    domain = _extract_domain_from_hostname(host.hostnames)
                if domain is not None:
                    drafts.append(
                        {
                            "type": "windows.domain",
                            "value": {
                                "name": domain,
                                "domain_controller": service.host or target,
                                "forest": forest,
                            },
                            "target_ref": target_ref,
                            "source_id": self._action_id,
                            "source_execution_id": execution_id,
                            "confidence": 0.75,
                            "sensitivity": "internal",
                            "metadata": {"parser": "nmap_xml", "source": "smb-os-discovery"},
                        }
                    )
                role = (
                    "domain_controller"
                    if _is_domain_controller(host.os_matches, service.product)
                    else "member_server"
                )
                drafts.append(
                    {
                        "type": "windows.host_role",
                        "value": {"host_ref": target_ref, "role": role},
                        "target_ref": target_ref,
                        "source_id": self._action_id,
                        "source_execution_id": execution_id,
                        "confidence": 0.7,
                        "sensitivity": "internal",
                        "metadata": {"parser": "nmap_xml"},
                    }
                )
                drafts.append(
                    self._observation_draft(
                        request=request,
                        context=context,
                        execution_id=execution_id,
                        target_ref=target_ref,
                        title="SMB service configuration observed",
                        description=(
                            "SMB service detected on port "
                            f"{service.port}; protocol and OS metadata observed "
                            "from Nmap script output."
                        ),
                        evidence={
                            "port": service.port,
                            "protocol": service.protocol,
                            "product": service.product,
                            "version": service.version,
                            "scripts": dict(service.scripts),
                            "os_matches": list(host.os_matches),
                        },
                        source_artifact_id=None,
                        severity="info",
                        confidence=0.8,
                        remediation=(
                            "Review SMB protocol versions and disable legacy "
                            "dialects (SMBv1) where not required. Restrict SMB "
                            "exposure to authorized subnets."
                        ),
                    )
                )
        return drafts


# ---------------------------------------------------------------------------
# windows.ldap.domain_inventory
# ---------------------------------------------------------------------------


class LdapDomainInventoryHandler(ReadOnlyToolHandler):
    """Read-only LDAP service and domain inventory."""

    def __init__(
        self, executor: ActionHandler | None = None, adapter: ToolAdapter | None = None
    ) -> None:
        super().__init__(
            executor or ProcessExecutor(executable="nmap"),
            adapter or NmapAdapter(),
            action_id="windows.ldap.domain_inventory",
        )

    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        port = int(str(request.inputs.get("port", 389)))
        return {
            "target": str(request.inputs.get("target", "")),
            "ports": str(port),
        }

    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        drafts: list[dict[str, object]] = []
        target = str(request.inputs.get("target", ""))
        port = int(str(request.inputs.get("port", 389)))
        for host in result.hosts:
            for service in host.services:
                if service.state != "open" or service.port != port:
                    continue
                target_ref = service.host or target
                domain = _extract_domain_from_hostname(host.hostnames)
                if domain is not None:
                    drafts.append(
                        {
                            "type": "windows.domain",
                            "value": {
                                "name": domain,
                                "domain_controller": service.host or target,
                                "forest": None,
                            },
                            "target_ref": target_ref,
                            "source_id": self._action_id,
                            "source_execution_id": execution_id,
                            "confidence": 0.6,
                            "sensitivity": "internal",
                            "metadata": {"parser": "nmap_xml", "source": "ldap-service-metadata"},
                        }
                    )
                drafts.append(
                    self._observation_draft(
                        request=request,
                        context=context,
                        execution_id=execution_id,
                        target_ref=target_ref,
                        title="LDAP service inventory observed",
                        description=(
                            "LDAP service detected on port "
                            f"{service.product or service.port}; directory "
                            "domain was not authoritatively enumerated."
                        ),
                        evidence={
                            "port": service.port,
                            "protocol": service.protocol,
                            "service_name": service.service_name,
                            "product": service.product,
                            "version": service.version,
                            "hostnames": list(host.hostnames),
                            "domain_from_hostname": domain,
                        },
                        source_artifact_id=None,
                        severity="info",
                        confidence=0.7,
                        remediation=(
                            "Confirm LDAP is bound to authorized interfaces and "
                            "that directory queries require authentication. "
                            "Prefer LDAPS (port 636) where supported."
                        ),
                    )
                )
        return drafts


# ---------------------------------------------------------------------------
# windows.http.method_observation
# ---------------------------------------------------------------------------


class HttpMethodObservationHandler(ReadOnlyToolHandler):
    """Non-mutating observation of advertised HTTP methods."""

    def __init__(
        self, executor: ActionHandler | None = None, adapter: ToolAdapter | None = None
    ) -> None:
        super().__init__(
            executor or ProcessExecutor(executable="nmap"),
            adapter or NmapAdapter(),
            action_id="windows.http.method_observation",
        )

    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        port = int(str(request.inputs.get("port", 80)))
        return {
            "target": str(request.inputs.get("target", "")),
            "ports": str(port),
            "scripts": "http-methods",
        }

    @staticmethod
    def _parse_advertised_methods(script_output: str) -> list[str]:
        seen: list[str] = []
        for match in _HTTP_METHOD_RE.finditer(script_output):
            method = match.group(0).upper()
            if method not in seen:
                seen.append(method)
        return seen

    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        drafts: list[dict[str, object]] = []
        target = str(request.inputs.get("target", ""))
        port = int(str(request.inputs.get("port", 80)))
        for host in result.hosts:
            for service in host.services:
                if service.state != "open" or service.port != port:
                    continue
                target_ref = service.host or target
                methods = self._parse_advertised_methods(
                    service.scripts.get("http-methods", "")
                )
                drafts.append(
                    self._observation_draft(
                        request=request,
                        context=context,
                        execution_id=execution_id,
                        target_ref=target_ref,
                        title="HTTP methods advertised",
                        description=(
                            f"HTTP service on port {service.port} advertises "
                            f"{', '.join(methods) if methods else 'no methods '
                            'from script output'}. These are observations only "
                            "and do not prove exploitability."
                        ),
                        evidence={
                            "port": service.port,
                            "protocol": service.protocol,
                            "service_name": service.service_name,
                            "advertised_methods": methods,
                            "http_methods_script": service.scripts.get("http-methods"),
                        },
                        source_artifact_id=None,
                        severity="info",
                        confidence=0.8,
                        remediation=(
                            "Disable HTTP methods not required by the "
                            "application (for example PUT, DELETE, TRACE) and "
                            "review advertised methods as part of attack-surface "
                            "reduction. Advertised methods alone are not a "
                            "vulnerability."
                        ),
                    )
                )
        return drafts


# ---------------------------------------------------------------------------
# windows.rdp.exposure_observation
# ---------------------------------------------------------------------------


class RdpExposureObservationHandler(ReadOnlyToolHandler):
    """Read-only observation of RDP exposure and configuration."""

    def __init__(
        self, executor: ActionHandler | None = None, adapter: ToolAdapter | None = None
    ) -> None:
        super().__init__(
            executor or ProcessExecutor(executable="nmap"),
            adapter or NmapAdapter(),
            action_id="windows.rdp.exposure_observation",
        )

    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        port = int(str(request.inputs.get("port", 3389)))
        return {
            "target": str(request.inputs.get("target", "")),
            "ports": str(port),
            "scripts": "rdp-enum-encryption",
        }

    @staticmethod
    def _parse_security_layer(script_output: str) -> str | None:
        for line in script_output.splitlines():
            low = line.lower()
            if low.startswith("security layer") or "security layer" in low:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
        return None

    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        drafts: list[dict[str, object]] = []
        target = str(request.inputs.get("target", ""))
        port = int(str(request.inputs.get("port", 3389)))
        for host in result.hosts:
            for service in host.services:
                if service.state != "open" or service.port != port:
                    continue
                target_ref = service.host or target
                security_layer = self._parse_security_layer(
                    service.scripts.get("rdp-enum-encryption", "")
                )
                drafts.append(
                    self._observation_draft(
                        request=request,
                        context=context,
                        execution_id=execution_id,
                        target_ref=target_ref,
                        title="RDP exposure observed",
                        description=(
                            f"RDP service detected on port {service.port} "
                            f"(security layer: {security_layer or 'not '
                            'observed'}). Configuration observation only; no "
                            "authentication is attempted."
                        ),
                        evidence={
                            "port": service.port,
                            "protocol": service.protocol,
                            "service_name": service.service_name,
                            "product": service.product,
                            "security_layer": security_layer,
                            "rdp_script": service.scripts.get("rdp-enum-encryption"),
                        },
                        source_artifact_id=None,
                        severity="info",
                        confidence=0.8,
                        remediation=(
                            "Restrict RDP to authorized networks, require "
                            "Network Level Authentication (NLA), and keep the "
                            "host patched. Exposure observation is not a "
                            "finding by itself."
                        ),
                    )
                )
        return drafts


# ---------------------------------------------------------------------------
# windows.winrm.exposure_observation
# ---------------------------------------------------------------------------


class WinrmExposureObservationHandler(ReadOnlyToolHandler):
    """Read-only observation of WinRM exposure and configuration."""

    def __init__(
        self, executor: ActionHandler | None = None, adapter: ToolAdapter | None = None
    ) -> None:
        super().__init__(
            executor or ProcessExecutor(executable="nmap"),
            adapter or NmapAdapter(),
            action_id="windows.winrm.exposure_observation",
        )

    def _build_inputs(self, request: ActionRequest) -> dict[str, object]:
        port = int(str(request.inputs.get("port", 5985)))
        return {
            "target": str(request.inputs.get("target", "")),
            "ports": str(port),
            "scripts": "winrm-info",
        }

    def _drafts_from_result(
        self,
        result: NmapParseResult,
        request: ActionRequest,
        context: ActionExecutionContext,
        execution_id: str,
    ) -> list[dict[str, object]]:
        drafts: list[dict[str, object]] = []
        target = str(request.inputs.get("target", ""))
        port = int(str(request.inputs.get("port", 5985)))
        for host in result.hosts:
            for service in host.services:
                if service.state != "open" or service.port != port:
                    continue
                target_ref = service.host or target
                drafts.append(
                    self._observation_draft(
                        request=request,
                        context=context,
                        execution_id=execution_id,
                        target_ref=target_ref,
                        title="WinRM exposure observed",
                        description=(
                            f"WinRM service detected on port {service.port}. "
                            "Configuration observation only; no authentication "
                            "or remote command execution is attempted."
                        ),
                        evidence={
                            "port": service.port,
                            "protocol": service.protocol,
                            "service_name": service.service_name,
                            "product": service.product,
                            "version": service.version,
                            "winrm_script": service.scripts.get("winrm-info"),
                        },
                        source_artifact_id=None,
                        severity="info",
                        confidence=0.8,
                        remediation=(
                            "Restrict WinRM to authorized networks, use "
                            "HTTPS/encryption where supported, and enforce "
                            "authentication. Exposure observation is not a "
                            "finding by itself."
                        ),
                    )
                )
        return drafts


__all__ = [
    "NmapServiceDiscoveryHandler",
    "SmbConfigurationAuditHandler",
    "LdapDomainInventoryHandler",
    "HttpMethodObservationHandler",
    "RdpExposureObservationHandler",
    "WinrmExposureObservationHandler",
    "ReadOnlyToolHandler",
]
