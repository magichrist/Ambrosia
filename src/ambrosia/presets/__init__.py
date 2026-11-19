"""Preset system: declarative YAML/JSON action workflow definitions.

Public interface:

* :class:`~ambrosia.presets.loader.PresetLoader` -- load and validate preset
  documents against a registry, and run dry-runs.
* :class:`~ambrosia.presets.loader.LoadedPreset`, :class:`~ambrosia.presets.loader.DryRunResult`
* :class:`~ambrosia.presets.plan.StepNode`, :class:`~ambrosia.presets.plan.PresetPlan`,
  :func:`~ambrosia.presets.plan.build_plan`
* :class:`~ambrosia.presets.resolution.Resolver`,
  :class:`~ambrosia.presets.resolution.ResolutionContext`
* :class:`~ambrosia.presets.references.VariableReference`,
  :func:`~ambrosia.presets.references.parse_reference`
* :class:`~ambrosia.presets.predicates.Predicate`,
  :func:`~ambrosia.presets.predicates.parse_predicate`,
  :func:`~ambrosia.presets.predicates.evaluate_predicate`
* Errors and structured resolution requests:
  :class:`~ambrosia.presets.errors.PresetValidationError`,
  :class:`~ambrosia.presets.errors.DuplicateStepIdError`,
  :class:`~ambrosia.presets.errors.CyclicDependencyError`,
  :class:`~ambrosia.presets.errors.UnresolvedActionError`,
  :class:`~ambrosia.presets.errors.InvalidReferenceError`,
  :class:`~ambrosia.presets.errors.InvalidPredicateError`,
  :class:`~ambrosia.presets.errors.TypeMismatchError`,
  :class:`~ambrosia.presets.errors.InputRequest`,
  :class:`~ambrosia.presets.errors.ArtifactSelectionRequest`,
  :class:`~ambrosia.presets.errors.SecretHandle`

Domain contracts (re-exported for convenience):
:class:`~ambrosia.domain.preset.PresetDefinition`,
:class:`~ambrosia.domain.preset.PresetStep`,
:class:`~ambrosia.domain.preset.PresetInput`,
:class:`~ambrosia.domain.preset.OutputBinding`

YAML is loaded with ``yaml.safe_load`` only. Python object tags, arbitrary
expressions, and exec/eval-style substitution are never permitted.
"""

from __future__ import annotations

from ambrosia.domain.preset import (
    OutputBinding,
    PresetDefinition,
    PresetInput,
    PresetStep,
)
from ambrosia.presets.errors import (
    ArtifactSelectionRequest,
    CyclicDependencyError,
    DuplicateStepIdError,
    InputRequest,
    InvalidPredicateError,
    InvalidReferenceError,
    PresetError,
    PresetValidationError,
    SecretHandle,
    TypeMismatchError,
    UnresolvedActionError,
)
from ambrosia.presets.loader import DryRunResult, LoadedPreset, PresetLoader
from ambrosia.presets.plan import Binding, BranchMap, PresetPlan, StepNode, build_plan
from ambrosia.presets.predicates import Predicate, evaluate_predicate, parse_predicate
from ambrosia.presets.references import VariableReference, parse_reference
from ambrosia.presets.resolution import (
    DeferredStepOutput,
    ResolutionContext,
    ResolvedValue,
    Resolver,
    check_type,
)

__all__ = [
    # domain contracts (re-exported)
    "OutputBinding",
    "PresetDefinition",
    "PresetInput",
    "PresetStep",
    # loader
    "LoadedPreset",
    "DryRunResult",
    "PresetLoader",
    # plan
    "Binding",
    "BranchMap",
    "StepNode",
    "PresetPlan",
    "build_plan",
    # resolution
    "Resolver",
    "ResolutionContext",
    "ResolvedValue",
    "DeferredStepOutput",
    "check_type",
    # references
    "VariableReference",
    "parse_reference",
    # predicates
    "Predicate",
    "parse_predicate",
    "evaluate_predicate",
    # errors / structured requests
    "PresetError",
    "PresetValidationError",
    "DuplicateStepIdError",
    "CyclicDependencyError",
    "UnresolvedActionError",
    "InvalidReferenceError",
    "InvalidPredicateError",
    "TypeMismatchError",
    "InputRequest",
    "ArtifactSelectionRequest",
    "SecretHandle",
]
