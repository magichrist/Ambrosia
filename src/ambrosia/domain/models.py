"""Core domain models: engagement, scope, artifact, execution record.

Pydantic v2 models with explicit validation. No SQLAlchemy, Textual, or Typer
imports allowed in this module.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    return datetime.utcnow()


_HOSTNAME_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))*$")
_DOMAIN_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))+\.?$")


def _new_id() -> str:
    return str(uuid4())


class Engagement(BaseModel):
    """A named unit of work with its own scope, targets, context, artifacts."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: Literal["active", "paused", "archived"] = "active"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    scope_id: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("engagement name must not be empty")
        return v.strip()


class Scope(BaseModel):
    """Explicit authorization boundary for an engagement.

    Defaults are conservative. An empty scope does NOT mean allow all.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    engagement_id: str = Field(min_length=1)
    include_hosts: list[str] = Field(default_factory=list)
    include_cidrs: list[str] = Field(default_factory=list)
    include_domains: list[str] = Field(default_factory=list)
    exclude_hosts: list[str] = Field(default_factory=list)
    exclude_cidrs: list[str] = Field(default_factory=list)
    allowed_ports: list[int] | None = None
    expires_at: datetime | None = None
    max_concurrency: int = Field(default=2, ge=1)
    max_requests_per_second: float | None = Field(default=None, ge=0)
    allowed_effects: set[str] = Field(default_factory=lambda: {"local_read", "network_observe"})
    require_approval_for: set[str] = Field(
        default_factory=lambda: {"local_write", "remote_change", "authentication"}
    )

    @model_validator(mode="after")
    def _no_include_exclude_overlap(self) -> Scope:
        include = set(self.include_hosts) | set(self.include_cidrs) | set(self.include_domains)
        exclude = set(self.exclude_hosts) | set(self.exclude_cidrs)
        overlap = include & exclude
        if overlap:
            raise ValueError(f"hosts/cidrs/domains appear in both include and exclude: {sorted(overlap)}")
        return self


class Artifact(BaseModel):
    """Immutable typed item of information with provenance.

    ``value`` must not contain raw secret material. Use ``secret_ref`` for
    sensitive data. Only opaque references are persisted.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    engagement_id: str = Field(min_length=1)
    type: str = Field(min_length=1)  # namespaced, e.g. network.host, windows.domain
    value: dict[str, object] = Field(default_factory=dict)
    source_kind: Literal["action", "preset", "operator", "import"] = "operator"
    source_id: str | None = None
    source_execution_id: str | None = None
    target_ref: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: Literal["public", "internal", "sensitive", "secret"] = "internal"
    secret_ref: str | None = None
    scope_binding: dict[str, object] | None = None
    supersedes: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_secret_in_value(self) -> Artifact:
        # Lightweight hint: reject obviously-secret keys in dict values.
        # Artifact subclasses with typed value schemas carry non-dict values;
        # those are validated by their own schema instead of here.
        if not isinstance(self.value, dict):
            return self
        secret_keys = {"password", "passwd", "secret", "token", "key", "credential", "hash"}
        for k in self.value:
            if k.lower() in secret_keys:
                raise ValueError(f"artifact value must not contain raw secret material: key={k!r}")
        return self


ExecutionStatus = Literal[
    "draft",
    "validated",
    "awaiting_input",
    "awaiting_approval",
    "ready",
    "running",
    "parsing",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "blocked",
]


class ExecutionRecord(BaseModel):
    """One attempt to run an action or preset."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    engagement_id: str = Field(min_length=1)
    action_id: str | None = None
    preset_id: str | None = None
    status: ExecutionStatus = "draft"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    target_refs: list[str] = Field(default_factory=list)
    input_summary: dict[str, object] = Field(default_factory=dict)
    output_artifact_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    initiated_by: str = "operator"

    @model_validator(mode="after")
    def _input_summary_redacts_secrets(self) -> ExecutionRecord:
        secret_keys = {"password", "passwd", "secret", "token", "key", "credential", "hash"}
        for k in self.input_summary:
            if k.lower() in secret_keys:
                raise ValueError("input_summary must not contain raw secret material")
        return self


class Target(BaseModel):
    """An engagement-authorized target: a host, IP address, or domain.

    The address is validated against its declared ``kind``. Targets are the
    unit of scope binding: artifacts carry ``target_ref`` so that evidence
    from one host never silently becomes evidence about another.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    engagement_id: str = Field(min_length=1)
    address: str = Field(min_length=1)
    kind: Literal["host", "ip", "domain"]
    scope_ref: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("address")
    @classmethod
    def _address_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            message = "target address must not be empty"
            raise ValueError(message)
        return v

    @model_validator(mode="after")
    def _address_matches_kind(self) -> Target:
        if self.kind == "ip":
            try:
                ipaddress.ip_address(self.address)
            except ValueError as exc:
                message = f"target address is not a valid IP: {self.address!r}"
                raise ValueError(message) from exc
        elif self.kind == "domain":
            if not _DOMAIN_RE.fullmatch(self.address):
                message = f"target address is not a valid domain: {self.address!r}"
                raise ValueError(message)
        elif self.kind == "host":
            if not _HOSTNAME_RE.fullmatch(self.address):
                message = f"target address is not a valid hostname: {self.address!r}"
                raise ValueError(message)
        return self


_SECRET_EVIDENCE_KEYS = {"password", "passwd", "secret", "token", "key", "credential", "hash"}


def _assert_no_secret_material(mapping: dict[str, object], what: str) -> None:
    for key in mapping:
        if key.lower() in _SECRET_EVIDENCE_KEYS:
            message = f"{what} must not contain raw secret material: key={key!r}"
            raise ValueError(message)


class Observation(BaseModel):
    """A technical fact or raw assessment result, not yet judged to be a finding.

    Evidence and impact/remediation are non-secret. Provenance is retained via
    ``source_artifact_id`` and ``target_ref`` so an observation about host A
    cannot silently be treated as one about host B.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    engagement_id: str = Field(min_length=1)
    target_ref: str | None = None
    source_artifact_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    evidence: dict[str, object] = Field(default_factory=dict)
    impact: str | None = None
    remediation: str | None = None
    severity: Literal["info", "low", "moderate", "high", "critical"] = "info"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _no_secret_in_evidence(self) -> Observation:
        _assert_no_secret_material(self.evidence, "observation evidence")
        return self


class Finding(BaseModel):
    """A validated security issue or policy deviation with evidence, impact,
    and remediation guidance.

    Like :class:`Observation`, it retains source-artifact and target
    provenance and never stores raw secret material.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    engagement_id: str = Field(min_length=1)
    target_ref: str | None = None
    source_artifact_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    evidence: dict[str, object] = Field(default_factory=dict)
    impact: str | None = None
    remediation: str | None = None
    severity: Literal["info", "low", "moderate", "high", "critical"] = "info"
    status: Literal["open", "resolved", "false_positive", "accepted"] = "open"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _no_secret_in_evidence(self) -> Finding:
        _assert_no_secret_material(self.evidence, "finding evidence")
        return self
