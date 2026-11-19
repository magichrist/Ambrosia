"""Base classes and shared data structures for read-only tool adapters.

Adapters translate resolved action inputs into an argv array for a fixed,
allowlisted executable, and parse that executable's machine-readable output
into structured results. They contain no credential material and perform
read-only observation only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class NmapHost:
    """A single host parsed from Nmap XML output."""

    address: str
    hostnames: list[str] = field(default_factory=list)
    services: list[NmapService] = field(default_factory=list)
    os_matches: list[str] = field(default_factory=list)


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
]
