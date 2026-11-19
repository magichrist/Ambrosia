"""Context namespaces and context events.

Context is an engagement-scoped, queryable view over operator inputs and
artifacts. It does not duplicate every artifact as arbitrary variables.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ContextNamespace(BaseModel):
    """Well-defined context namespaces exposed to the matcher/resolver."""

    model_config = ConfigDict(extra="forbid")

    engagement: dict[str, object] = {}
    scope: dict[str, object] = {}
    target: dict[str, object] = {}
    selected_target: dict[str, object] = {}
    artifacts: dict[str, object] = {}
    facts: dict[str, object] = {}
    last_execution: dict[str, object] = {}
    user: dict[str, object] = {}


class ContextEvent(BaseModel):
    """Explicit event driving UI reactivity and history persistence.

    Events contain IDs and safe summaries, never secret values.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "EngagementSelected",
        "ScopeChanged",
        "TargetAdded",
        "ArtifactCreated",
        "ArtifactSuperseded",
        "ExecutionStateChanged",
        "ActionAvailabilityChanged",
        "PhaseConfigurationChanged",
        "PresetSaved",
        "PolicyDecisionRecorded",
    ]
    engagement_id: str
    payload: dict[str, object] = {}
    timestamp: str | None = None
