"""Built-in artifact type definitions.

Each artifact type is a Pydantic model wrapping the shared :class:`ambrosia.domain.models.Artifact`
with a type-specific, validated ``value`` schema. Only opaque references are
ever stored; raw secret material is rejected by the base ``Artifact`` model.

These models import only the domain layer (contracts). They know nothing about
storage, TUI, CLI, or executors.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ambrosia.domain.models import Artifact, Finding, Observation


class HostValue(BaseModel):
    """Value payload for a ``network.host`` artifact."""

    model_config = ConfigDict(extra="forbid")

    hostname: str | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    domain: str | None = None
    operating_system: str | None = None
    mac_address: str | None = None

    @field_validator("ip_addresses")
    @classmethod
    def _validate_ips(cls, values: list[str]) -> list[str]:
        import ipaddress

        for ip in values:
            try:
                ipaddress.ip_address(ip)
            except ValueError as exc:
                message = f"invalid IP address in host value: {ip!r}"
                raise ValueError(message) from exc
        return values


class ServiceValue(BaseModel):
    """Value payload for a ``network.service`` artifact."""

    model_config = ConfigDict(extra="forbid")

    host_ref: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp", "udp", "icmp"] = "tcp"
    service_name: str | None = None
    product: str | None = None
    version: str | None = None
    state: Literal["open", "closed", "filtered"] = "open"


class DomainValue(BaseModel):
    """Value payload for a ``windows.domain`` artifact."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    domain_controller: str | None = None  # host_ref of a domain controller
    forest: str | None = None


class HostRoleValue(BaseModel):
    """Value payload for a ``windows.host_role`` artifact."""

    model_config = ConfigDict(extra="forbid")

    host_ref: str = Field(min_length=1)
    role: Literal[
        "domain_controller", "member_server", "workstation", "standalone_server"
    ]


class UserRefValue(BaseModel):
    """Value payload for an ``identity.user_ref`` artifact (reference only)."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1)
    domain: str | None = None
    sid: str | None = None
    is_service_account: bool = False


class SecretRefValue(BaseModel):
    """Value payload for a ``secret.ref`` artifact.

    Holds an opaque secret handle and metadata only. Never the secret value.
    """

    model_config = ConfigDict(extra="forbid")

    secret_ref: str = Field(min_length=1)
    secret_type: Literal["password", "hash", "key", "token", "certificate"] = "password"  # noqa: S105  # metadata label, not a secret value
    label: str | None = None


class EvidenceRefValue(BaseModel):
    """Value payload for an ``evidence.ref`` artifact.

    References evidence stored under the application data directory by
    generated ID. Never embeds file contents.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    path: str | None = None  # safe path reference, not a user-provided path
    content_hash: str | None = None
    media_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Artifact wrappers (type-specific value schemas)
# ---------------------------------------------------------------------------


class HostArtifact(Artifact):
    """``network.host`` — a discovered host."""

    type: Literal["network.host"] = "network.host"
    value: HostValue  # type: ignore[assignment]  # narrows base Artifact.value (dict) to the typed schema


class ServiceArtifact(Artifact):
    """``network.service`` — a discovered network service on a host."""

    type: Literal["network.service"] = "network.service"
    value: ServiceValue  # type: ignore[assignment]


class DomainArtifact(Artifact):
    """``windows.domain`` — a discovered Windows/AD domain."""

    type: Literal["windows.domain"] = "windows.domain"
    value: DomainValue  # type: ignore[assignment]


class HostRoleArtifact(Artifact):
    """``windows.host_role`` — the role of a Windows host."""

    type: Literal["windows.host_role"] = "windows.host_role"
    value: HostRoleValue  # type: ignore[assignment]


class UserRefArtifact(Artifact):
    """``identity.user_ref`` — a reference to an identity account."""

    type: Literal["identity.user_ref"] = "identity.user_ref"
    value: UserRefValue  # type: ignore[assignment]


class SecretRefArtifact(Artifact):
    """``secret.ref`` — an opaque reference to secret material."""

    type: Literal["secret.ref"] = "secret.ref"
    value: SecretRefValue  # type: ignore[assignment]


class EvidenceRefArtifact(Artifact):
    """``evidence.ref`` — a reference to a piece of stored evidence."""

    type: Literal["evidence.ref"] = "evidence.ref"
    value: EvidenceRefValue  # type: ignore[assignment]


class ObservationArtifact(Artifact):
    """``observation`` — a technical observation with evidence and provenance."""

    type: Literal["observation"] = "observation"
    value: Observation  # type: ignore[assignment]


class FindingArtifact(Artifact):
    """``finding`` — a validated finding with evidence, impact, remediation."""

    type: Literal["finding"] = "finding"
    value: Finding  # type: ignore[assignment]


# Mapping of namespaced artifact type -> wrapper class.
TYPE_REGISTRY: dict[str, type[Artifact]] = {
    "network.host": HostArtifact,
    "network.service": ServiceArtifact,
    "windows.domain": DomainArtifact,
    "windows.host_role": HostRoleArtifact,
    "identity.user_ref": UserRefArtifact,
    "secret.ref": SecretRefArtifact,
    "evidence.ref": EvidenceRefArtifact,
    "observation": ObservationArtifact,
    "finding": FindingArtifact,
}

__all__ = [
    "HostValue",
    "ServiceValue",
    "DomainValue",
    "HostRoleValue",
    "UserRefValue",
    "SecretRefValue",
    "EvidenceRefValue",
    "HostArtifact",
    "ServiceArtifact",
    "DomainArtifact",
    "HostRoleArtifact",
    "UserRefArtifact",
    "SecretRefArtifact",
    "EvidenceRefArtifact",
    "ObservationArtifact",
    "FindingArtifact",
    "TYPE_REGISTRY",
]
