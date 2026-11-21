"""Workflow definitions for Ambrosia v2.

A :class:`Workflow` is a named, phase-ordered list of command ids. It lets an
operator group related commands (e.g. a Windows gain-access chain) into ordered
phases and load them from ``inventory/workflow/``. Workflows reference command
ids defined in :mod:`ambrosia.storage` presets — they do not contain command
definitions themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import yaml


@dataclass(frozen=True)
class Workflow:
    """A named, phase-ordered workflow of command ids.

    ``phases`` maps a phase name (e.g. ``"phase 1"``, ``"recon"``) to an
    ordered list of command ids that belong to that phase.
    """

    name: str
    phases: dict[str, list[str]] = field(default_factory=dict)

    def phase_names(self) -> list[str]:
        """Return phase names in declaration order."""
        return list(self.phases.keys())

    def command_ids(self, phase: str | None = None) -> list[str]:
        """Return all command ids, or those for a single ``phase``."""
        if phase is None:
            ids: list[str] = []
            for command_ids in self.phases.values():
                ids.extend(command_ids)
            return ids
        return list(self.phases.get(phase, []))

    def to_dict(self) -> dict[str, object]:
        """Serialize to a YAML-friendly dict."""
        return {
            "name": self.name,
            "phases": {phase: list(ids) for phase, ids in self.phases.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Deserialize from a YAML dict, tolerating missing keys."""
        name = str(data.get("name", ""))
        phases_raw = data.get("phases", {})
        phases: dict[str, list[str]] = {}
        if isinstance(phases_raw, dict):
            for phase, command_ids in phases_raw.items():
                if isinstance(command_ids, list):
                    phases[str(phase)] = [str(cid) for cid in command_ids]
        return cls(name=name, phases=phases)


class WorkflowStore:
    """Load :class:`Workflow` instances from ``.workflow`` YAML files."""

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)

    # ------------------------------------------------------------------ public API

    def load_file(self, path: Path) -> Workflow | None:
        """Load a single workflow from ``path``.

        Returns ``None`` if the file is missing or contains invalid YAML.
        """
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return None
        if not isinstance(data, dict):
            return None
        return Workflow.from_dict(data)

    def load_dir(self, directory: Path | None = None) -> list[Workflow]:
        """Load all workflows from ``directory`` (or this store's directory).

        Files are returned in sorted path order for deterministic loading.
        """
        target = Path(directory) if directory is not None else self._directory
        if not target.exists() or not target.is_dir():
            return []
        workflows: list[Workflow] = []
        for workflow_file in sorted(target.glob("*.workflow")):
            workflow = self.load_file(workflow_file)
            if workflow is not None:
                workflows.append(workflow)
        return workflows


def load_workflow_file(path: Path) -> Workflow | None:
    """Load a single workflow from ``path`` (module-level helper)."""
    return WorkflowStore(Path(path).parent).load_file(Path(path))


def load_workflows_from_dir(directory: Path) -> list[Workflow]:
    """Load all workflows from ``directory`` (module-level helper)."""
    return WorkflowStore(directory).load_dir()


__all__ = ["Workflow", "WorkflowStore", "load_workflow_file", "load_workflows_from_dir"]
