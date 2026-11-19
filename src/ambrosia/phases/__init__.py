"""Phase definitions: user-defined organizational labels.

A phase is a navigation/grouping label for actions and presets. It cannot
mandate the next phase, mutate context, or grant permission -- it is
organizational only.

Public interface:

* :class:`~ambrosia.phases.catalog.PhaseCatalog` -- load phases from files or a
  directory, list them, and look them up by id.
* :func:`~ambrosia.phases.catalog.load_phase_file`,
  :func:`~ambrosia.phases.catalog.load_phases_from_dir`

Domain contract (re-exported): :class:`~ambrosia.domain.phase.PhaseDefinition`,
:class:`~ambrosia.domain.phase.Predicate`.
"""

from __future__ import annotations

from ambrosia.domain.phase import PhaseDefinition, Predicate
from ambrosia.phases.catalog import (
    PhaseCatalog,
    load_phase_file,
    load_phases_from_dir,
)

__all__ = [
    "Predicate",
    "PhaseDefinition",
    "PhaseCatalog",
    "load_phase_file",
    "load_phases_from_dir",
]
