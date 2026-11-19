"""Read-only tool adapters.

Tool adapters wrap allowlisted assessment executables (for example Nmap). An
adapter knows how to build an argv array for its tool and how to parse the
tool's machine-readable output into structured results. Adapters never start
processes themselves -- an executor (:class:`ambrosia.executors.process.ProcessExecutor`
or a test fake) is responsible for execution -- and they never perform
credential access, mutation, persistence, evasion, or remote command execution.
"""

from __future__ import annotations

from ambrosia.executors.adapters.base import (
    NmapHost,
    NmapParseResult,
    NmapService,
    ToolAdapter,
)
from ambrosia.executors.adapters.nmap import NmapAdapter

__all__ = [
    "NmapAdapter",
    "NmapHost",
    "NmapParseResult",
    "NmapService",
    "ToolAdapter",
]
