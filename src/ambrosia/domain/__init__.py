"""Shared domain contracts for Ambrosia.

These are the integration boundary for all builder agents. Domain models must
not import SQLAlchemy, Textual, Typer, or any concrete executor/tool.

See docs/01_SHARED_CONTRACTS.md for the authoritative specification.
"""

from __future__ import annotations

from ambrosia.domain.action import (
    ActionAvailability,
    ActionDefinition,
    ArtifactRequirement,
    ExecutorReference,
    ToolDependency,
)
from ambrosia.domain.context import ContextEvent, ContextNamespace
from ambrosia.domain.errors import (
    AmbrosiaError,
    ConflictError,
    ExecutionCancelledError,
    ExecutionError,
    ExecutionTimeoutError,
    MissingDependencyError,
    MissingInputError,
    NotFoundError,
    ParseError,
    PolicyBlockedError,
    ScopeViolationError,
    ValidationError,
)
from ambrosia.domain.models import (
    Artifact,
    Engagement,
    ExecutionRecord,
    ExecutionStatus,
    Finding,
    Observation,
    Scope,
    Target,
)
from ambrosia.domain.phase import PhaseDefinition
from ambrosia.domain.preset import OutputBinding, PresetDefinition, PresetInput, PresetStep
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionHandler,
    ActionRequest,
    ArtifactRepository,
    EngagementRepository,
    ExecutionEvent,
    ExecutionRepository,
    SecretStore,
)

__all__ = [
    # errors
    "AmbrosiaError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "ScopeViolationError",
    "PolicyBlockedError",
    "MissingInputError",
    "MissingDependencyError",
    "ExecutionError",
    "ExecutionTimeoutError",
    "ExecutionCancelledError",
    "ParseError",
    # models
    "Engagement",
    "Scope",
    "Artifact",
    "ExecutionRecord",
    "ExecutionStatus",
    "Target",
    "Observation",
    "Finding",
    # action
    "ActionDefinition",
    "ActionAvailability",
    "ExecutorReference",
    "ToolDependency",
    "ArtifactRequirement",
    # preset
    "PresetDefinition",
    "PresetStep",
    "PresetInput",
    "OutputBinding",
    # phase
    "PhaseDefinition",
    # protocols
    "EngagementRepository",
    "ArtifactRepository",
    "ExecutionRepository",
    "ActionHandler",
    "SecretStore",
    "ActionExecutionContext",
    "ActionRequest",
    "ExecutionEvent",
    # context
    "ContextNamespace",
    "ContextEvent",
]
