"""Phase catalog: loading and listing phase definitions.

Phases are user-defined organizational metadata: they group actions and
presets for navigation, carry display metadata, and may define optional
context predicates for *surfacing* a phase in the UI. A phase never grants
permission, never mutates context, and never forces lifecycle order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # types-PyYAML stubs are not a project dependency

from ambrosia.domain.errors import ParseError
from ambrosia.domain.phase import PhaseDefinition
from ambrosia.presets.predicates import evaluate_predicate, parse_predicate

_YAML_EXTENSIONS = frozenset({".yaml", ".yml", ".json"})


@dataclass(frozen=True)
class PhaseCatalog:
    """An immutable catalog of loaded phase definitions.

    Phases are organizational only: this catalog provides lookup and listing
    and no mechanism to grant permission or sequence the engagement lifecycle.
    """

    phases: dict[str, PhaseDefinition]

    def get(self, phase_id: str) -> PhaseDefinition | None:
        """Return the phase with the given id, or ``None``."""
        return self.phases.get(phase_id)

    def all(self) -> list[PhaseDefinition]:
        """Return all phases sorted by ``sort_order`` then id (deterministic)."""
        return sorted(
            self.phases.values(),
            key=lambda phase: (phase.sort_order, phase.id),
        )

    def ids(self) -> tuple[str, ...]:
        """Return all phase ids (deterministic order)."""
        return tuple(phase.id for phase in self.all())

    def unknown_refs(self, refs: list[str]) -> list[str]:
        """Return phase ids from ``refs`` that are not in the catalog."""
        return sorted(ref for ref in refs if ref not in self.phases)

    def phase_refs_for_preset(self, preset_id: str) -> tuple[str, ...]:
        """Phase ids that reference the given preset (navigation metadata only)."""
        return tuple(
            phase.id for phase in self.all() if preset_id in phase.preset_refs
        )

    def evaluate_visibility(
        self,
        phase_id: str,
        *,
        artifacts: list[Any],
        inputs: dict[str, object],
    ) -> bool:
        """Evaluate a phase's ``visible_when`` predicates (AND semantics).

        Pure and side-effect free. Used by the UI to decide whether to surface
        a phase; it carries no authorization semantics.
        """
        phase = self.phases.get(phase_id)
        if phase is None:
            return False
        if not phase.visible_when:
            return True
        results: list[bool] = []
        for predicate in phase.visible_when:
            parsed = parse_predicate(predicate.model_dump())
            if parsed is None:  # pragma: no cover - guarded by Predicate validation
                continue
            results.append(
                evaluate_predicate(parsed, artifacts=artifacts, inputs=inputs)
            )
        return all(results)


def load_phase_file(path: str | Path, source: str | None = None) -> PhaseDefinition:
    """Load and validate a single phase document from YAML/JSON."""
    path = Path(path)
    source = source or str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"{source}: cannot read phase: {exc}") from exc  # noqa: TRY003
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ParseError(f"{source}: invalid YAML: {exc}") from exc  # noqa: TRY003
    if not isinstance(data, dict):
        raise ParseError(f"{source}: phase document must be a mapping")  # noqa: TRY003
    try:
        return PhaseDefinition.model_validate(data)
    except Exception as exc:  # pragma: no cover - pydantic raises ValidationError
        raise ParseError(f"{source}: invalid phase document: {exc}") from exc  # noqa: TRY003


def load_phases_from_dir(directory: str | Path) -> PhaseCatalog:
    """Load all phase documents from a directory (YAML/JSON, deterministic order)."""
    directory = Path(directory)
    phases: dict[str, PhaseDefinition] = {}
    files = sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _YAML_EXTENSIONS),
        key=lambda p: p.name,
    )
    for path in files:
        phase = load_phase_file(path)
        if phase.id in phases:
            raise ValueError(f"duplicate phase id {phase.id!r} in {path}")  # noqa: TRY003
        phases[phase.id] = phase
    return PhaseCatalog(phases=phases)


__all__ = [
    "PhaseCatalog",
    "load_phase_file",
    "load_phases_from_dir",
]
