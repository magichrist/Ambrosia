"""Base classes and shared data structures for read-only tool adapters.

Adapters translate resolved action inputs into an argv array for a fixed,
allowlisted executable, and parse that executable's machine-readable output
into structured results. They contain no credential material and perform
read-only observation only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# ``ServiceValue.state`` (the artifact value model) accepts only these three
# literals. Nmap can emit combined states such as ``open|filtered`` (UDP scans
# and some filtered TCP scans), which would otherwise fail artifact validation.
_NMAP_STATE_LITERALS = ("open", "closed", "filtered")


def normalize_nmap_state(raw: str) -> str:
    """Map a raw Nmap port state onto the artifact state vocabulary.

    Exact ``open``/``closed``/``filtered`` states are preserved. Combined states
    are resolved to the most informative accepted value (``open|filtered`` ->
    ``open``, ``closed|filtered`` -> ``closed``); everything else is reported as
    ``filtered``. The original value is retained in ``NmapService.raw_state`` so
    no observation is silently lost.
    """
    lowered = raw.strip().lower()
    if lowered in _NMAP_STATE_LITERALS:
        return lowered
    if "open" in lowered:
        return "open"
    if "closed" in lowered:
        return "closed"
    return "filtered"


@dataclass(frozen=True)
class NmapService:
    """A single service entry parsed from Nmap XML output."""

    host: str
    port: int
    protocol: str
    state: str
    service_name: str | None = None
    product: str | None = None
    version: str | None = None
    scripts: dict[str, str] = field(default_factory=dict)
    """Raw NSE script output keyed by script id (never parsed as commands)."""
    raw_state: str | None = None
    """Original Nmap state string before normalisation (e.g. ``open|filtered``)."""


@dataclass(frozen=True)
class NmapHost:
    """A single host parsed from Nmap XML output."""

    address: str
    hostnames: list[str] = field(default_factory=list)
    services: list[NmapService] = field(default_factory=list)
    os_matches: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    """Host-level NSE script output (``<hostscript>``), keyed by script id."""


@dataclass(frozen=True)
class NmapParseResult:
    """Result of parsing Nmap XML output (``-oX -``)."""

    hosts: list[NmapHost] = field(default_factory=list)
    services: list[NmapService] = field(default_factory=list)

    @property
    def open_services(self) -> list[NmapService]:
        """Return services whose state is ``open``."""
        return [service for service in self.services if service.state == "open"]


class ToolAdapter(ABC):
    """Base class for read-only tool adapters.

    Concrete adapters declare a fixed ``executable`` (never sourced from an
    untrusted preset) and implement :meth:`build_argv` and
    :meth:`parse_output`.
    """

    executable: str = ""
    name: str = ""

    @abstractmethod
    def build_argv(self, **inputs: object) -> list[str]:
        """Build the argv array (executable excluded) for the tool.

        All values come from resolved, validated action inputs. Arguments are
        passed as data, never interpolated into a shell command string.
        """

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str = "") -> object:
        """Parse machine-readable tool output into a structured result."""


__all__ = [
    "NmapHost",
    "NmapParseResult",
    "NmapService",
    "ToolAdapter",
    "normalize_nmap_state",
]
