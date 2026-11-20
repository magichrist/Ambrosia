"""Nmap tool adapter.

Parses Nmap XML output (``-oX -``) into structured
:class:`~ambrosia.executors.adapters.base.NmapParseResult` instances. Nmap XML
is the structured, machine-readable output format; this adapter deliberately
does not parse Nmap's human-readable console or grepable output.

The adapter is read-only: it only builds bounded Nmap argv arrays and parses
returned XML. It never performs credential access, mutation, persistence,
evasion, or remote command execution.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from ambrosia.executors.adapters.base import (
    NmapHost,
    NmapParseResult,
    NmapService,
    ToolAdapter,
    normalize_nmap_state,
)

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


class NmapAdapter(ToolAdapter):
    """Adapter for the Nmap network scanner (read-only, bounded discovery)."""

    executable = "nmap"
    name = "nmap"

    def build_argv(self, **inputs: object) -> list[str]:
        """Build an Nmap argv array that emits XML to stdout.

        ``-oX -`` requests XML on stdout (structured, machine-readable).
        ``-Pn`` skips host discovery so the target is treated as up.
        ``-sV`` enables version detection for service identification. Only the
        declared ports are scanned, keeping the scan bounded to the authorized
        target and port list.

        Inputs are validated at runtime because the adapter contract accepts
        generic ``object`` values; invalid inputs raise :class:`ValueError`
        before any argv is produced.
        """
        target = inputs.get("target")
        ports = inputs.get("ports")
        if not isinstance(target, str) or not target:
            msg = "nmap adapter requires a non-empty 'target' string"
            raise ValueError(msg)
        if not isinstance(ports, str) or not ports:
            msg = "nmap adapter requires a non-empty 'ports' string"
            raise ValueError(msg)

        scripts = inputs.get("scripts")
        scripts_arg = str(scripts) if scripts is not None else None
        version_detection = bool(inputs.get("version_detection", True))

        argv: list[str] = [
            "-oX",
            "-",
            "-Pn",
            "-p",
            ports,
            target,
        ]
        if version_detection:
            argv.insert(2, "-sV")
        if scripts_arg:
            argv.extend(["--script", scripts_arg])
        return argv

    def parse_output(self, stdout: str, stderr: str = "") -> NmapParseResult:
        """Parse Nmap XML stdout into a :class:`NmapParseResult`.

        Returns an empty result for a scan with no hosts. Raises
        :class:`ValueError` when the output is not well-formed XML so callers
        can distinguish a parse failure from an empty scan.
        """
        if not stdout or not stdout.strip():
            return NmapParseResult()
        try:
            # Nmap XML is emitted by the locally invoked nmap binary, not by an
            # untrusted remote party; stdlib ElementTree does not resolve external entities.
            root = ET.fromstring(stdout)  # noqa: S314
        except ET.ParseError as exc:
            message = f"nmap XML output is not well-formed: {exc}"
            raise ValueError(message) from exc

        result = NmapParseResult()
        for host_elem in root.iter("host"):
            result.hosts.append(self._parse_host(host_elem))
        for host in result.hosts:
            result.services.extend(host.services)
        return result

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _parse_host(host_elem: Element) -> NmapHost:
        address_elem = host_elem.find("address")
        address = address_elem.get("addr", "") if address_elem is not None else ""

        hostnames: list[str] = []
        hostnames_elem = host_elem.find("hostnames")
        if hostnames_elem is not None:
            for hostname_elem in hostnames_elem.findall("hostname"):
                name = hostname_elem.get("name")
                if name:
                    hostnames.append(name)

        os_matches: list[str] = []
        os_elem = host_elem.find("os")
        if os_elem is not None:
            for osmatch in os_elem.findall("osmatch"):
                name = osmatch.get("name")
                if name:
                    os_matches.append(name)

        services: list[NmapService] = []
        ports_elem = host_elem.find("ports")
        if ports_elem is not None:
            for port_elem in ports_elem.findall("port"):
                services.append(NmapAdapter._parse_port(port_elem, address))

        # Host-level NSE output lives in <hostscript>, not under <ports>. Keep
        # it as opaque evidence text alongside port-level scripts so handlers
        # can consume it without treating it as commands.
        host_scripts: dict[str, str] = {}
        hostscript_elem = host_elem.find("hostscript")
        if hostscript_elem is not None:
            for script_elem in hostscript_elem.findall("script"):
                script_id = script_elem.get("id")
                if script_id is None:
                    continue
                output = script_elem.get("output")
                if output is None:
                    output = (script_elem.text or "").strip()
                host_scripts[script_id] = output

        return NmapHost(
            address=address,
            hostnames=hostnames,
            services=services,
            os_matches=os_matches,
            scripts=host_scripts,
        )

    @staticmethod
    def _parse_port(port_elem: Element, default_host: str) -> NmapService:
        port_id = port_elem.get("portid")
        protocol = port_elem.get("protocol", "tcp")
        try:
            port = int(port_id) if port_id is not None else 0
        except ValueError:
            port = 0

        state_elem = port_elem.find("state")
        raw_state = state_elem.get("state", "unknown") if state_elem is not None else "unknown"
        # Normalise combined states (e.g. "open|filtered") onto the artifact
        # vocabulary while retaining the raw observation.
        state = normalize_nmap_state(raw_state)

        service_name = None
        product = None
        version = None
        service_elem = port_elem.find("service")
        if service_elem is not None:
            service_name = service_elem.get("name") or None
            product = service_elem.get("product") or None
            version = service_elem.get("version") or None

        scripts: dict[str, str] = {}
        for script_elem in port_elem.findall("script"):
            script_id = script_elem.get("id")
            if script_id is None:
                continue
            output = script_elem.get("output")
            if output is None:
                output = (script_elem.text or "").strip()
            scripts[script_id] = output

        return NmapService(
            host=default_host,
            port=port,
            protocol=protocol,
            state=state,
            raw_state=raw_state,
            service_name=service_name,
            product=product,
            version=version,
            scripts=scripts,
        )


__all__ = ["NmapAdapter"]
