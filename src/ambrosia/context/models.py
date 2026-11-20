"""Context snapshot and derived-fact models.

A snapshot exposes the engagement-scoped queryable namespaces
(engagement, scope, target, selected_target, artifacts, facts,
last_execution, user) without duplicating every artifact in a mutable
dictionary. Artifacts are read from the repository at snapshot time.

Derived facts retain source-artifact ids and target provenance, so a fact
about host A can never silently be treated as a fact about host B.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # pydantic v2 must resolve `datetime` at runtime for forward-ref model rebuilds
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ambrosia.domain.context import ContextNamespace
from ambrosia.domain.models import _utc_now


class Fact(BaseModel):
    """A derived, typed fact with source-artifact and target provenance.

    ``source_artifact_id`` references the artifact the fact was derived from
    and ``target_ref`` records the target the fact is about. Together they
    prevent cross-host fact leakage.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    engagement_id: str = Field(min_length=1)
    target_ref: str | None = None
    source_artifact_id: str | None = None
    fact_type: str = Field(min_length=1)
    value: dict[str, object] = Field(default_factory=dict)
    derived_from: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime | None = None


class ContextSnapshot(BaseModel):
    """An engagement-scoped context snapshot exposing queryable namespaces."""

    model_config = ConfigDict(extra="forbid")

    engagement_id: str = Field(min_length=1)
    namespaces: ContextNamespace = Field(default_factory=ContextNamespace)
    generated_at: datetime = Field(default_factory=_utc_now)
    sequence: int = 0

    def namespace(
        self,
        name: Literal[
            "engagement",
            "scope",
            "target",
            "selected_target",
            "artifacts",
            "facts",
            "last_execution",
            "user",
        ],
    ) -> dict[str, object]:
        mapping: dict[str, dict[str, object]] = {
            "engagement": self.namespaces.engagement,
            "scope": self.namespaces.scope,
            "target": self.namespaces.target,
            "selected_target": self.namespaces.selected_target,
            "artifacts": self.namespaces.artifacts,
            "facts": self.namespaces.facts,
            "last_execution": self.namespaces.last_execution,
            "user": self.namespaces.user,
        }
        return mapping[name]

    def facts_map(self) -> dict[str, object]:
        return dict(self.namespaces.facts)

    def artifacts_map(self) -> dict[str, object]:
        return dict(self.namespaces.artifacts)
