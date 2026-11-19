"""Unit tests for built-in artifact types, validation, provenance, scoping."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from ambrosia.artifacts import (
    active_artifacts,
    artifacts_for_target,
    create_artifact,
    is_expired,
    match_required_artifacts,
    superseded_ids,
)
from ambrosia.artifacts.models import (
    TYPE_REGISTRY,
    HostArtifact,
    SecretRefArtifact,
    ServiceArtifact,
)
from ambrosia.domain.action import ArtifactRequirement
from ambrosia.domain.models import Artifact


def _future() -> datetime:
    return datetime.now() + timedelta(days=7)


def _past() -> datetime:
    return datetime.now() - timedelta(days=7)


# ---------------------------------------------------------------------------
# Valid artifact types and payloads
# ---------------------------------------------------------------------------

def test_valid_host_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1", "192.168.1.1"]},
        target_ref="target-a",
        sensitivity="internal",
        source_kind="action",
        source_id="nmap.discovery",
    )
    assert isinstance(artifact, HostArtifact)
    assert artifact.type == "network.host"
    assert artifact.engagement_id == "eng-1"
    assert artifact.value.hostname == "dc01"
    assert artifact.value.ip_addresses == ["10.0.0.1", "192.168.1.1"]
    assert artifact.target_ref == "target-a"
    assert artifact.sensitivity == "internal"


def test_valid_service_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="network.service",
        value={"host_ref": "host-1", "port": 445, "protocol": "tcp", "service_name": "smb"},
        target_ref="target-a",
    )
    assert isinstance(artifact, ServiceArtifact)
    assert artifact.value.port == 445
    assert artifact.value.state == "open"


def test_valid_secret_ref_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="secret.ref",
        value={"secret_ref": "vault://creds/1", "secret_type": "password", "label": "svc_acct"},
        target_ref="target-a",
        sensitivity="secret",
    )
    assert isinstance(artifact, SecretRefArtifact)
    assert artifact.value.secret_ref == "vault://creds/1"  # noqa: S105  # opaque secret handle, not a password
    assert artifact.sensitivity == "secret"


# ---------------------------------------------------------------------------
# Secret reference redaction / no raw secret material
# ---------------------------------------------------------------------------

def test_secret_value_in_payload_rejected() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="network.host",
            value={"hostname": "dc01", "password": "hunter2"},
        )


def test_secret_ref_is_opaque_reference_only() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="secret.ref",
        value={"secret_ref": "vault://creds/1", "secret_type": "password"},  # noqa: S105  # opaque secret handle, not a password
        target_ref="target-a",
        sensitivity="secret",
    )
    dumped = artifact.model_dump()
    # The opaque reference is present...
    assert dumped["value"]["secret_ref"] == "vault://creds/1"  # noqa: S105  # opaque secret handle, not a password
    # ...but no raw secret value is stored anywhere.
    text = str(dumped)
    assert "hunter2" not in text
    assert "secret" not in dumped  # artifact-level secret_ref not set


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------

def test_invalid_ip_rejected() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="network.host",
            value={"hostname": "bad", "ip_addresses": ["999.999.999.999"]},
        )


def test_port_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="network.service",
            value={"host_ref": "h", "port": 0},
        )
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="network.service",
            value={"host_ref": "h", "port": 70000},
        )


def test_unknown_artifact_type_falls_back_to_base() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="custom.thing",
        value={"foo": "bar"},
        target_ref="target-a",
    )
    assert isinstance(artifact, Artifact)
    assert not isinstance(artifact, HostArtifact)
    assert artifact.type == "custom.thing"


def test_all_built_in_types_registered() -> None:
    expected = {
        "network.host", "network.service", "windows.domain", "windows.host_role",
        "identity.user_ref", "secret.ref", "evidence.ref", "observation", "finding",
    }
    assert set(TYPE_REGISTRY) == expected


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_future_expiry_not_expired() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "x"},
        expires_at=_future(),
    )
    assert not is_expired(artifact)


def test_past_expiry_expired() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "x"},
        expires_at=_past(),
    )
    assert is_expired(artifact)


def test_expired_artifact_excluded_from_active_artifacts() -> None:
    active = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "live"},
        expires_at=_future(),
    )
    expired = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "dead"},
        expires_at=_past(),
    )
    assert not is_expired(active)
    assert is_expired(expired)

    active_ids = {a.id for a in active_artifacts([active, expired])}
    assert active.id in active_ids
    assert expired.id not in active_ids


def test_no_expiry_never_expired() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "x"},
    )
    assert not is_expired(artifact)


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------

def test_superseded_artifact_excluded_from_active() -> None:
    original = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.1"]},
        target_ref="target-a",
    )
    replacement = create_artifact(
        engagement_id="eng-1",
        type="network.host",
        value={"hostname": "dc01", "ip_addresses": ["10.0.0.2"]},
        target_ref="target-a",
        supersedes=original.id,
    )
    artifacts = [original, replacement]
    assert original.id in superseded_ids(artifacts)
    assert replacement.id not in superseded_ids(artifacts)

    active = active_artifacts(artifacts)
    active_ids = {a.id for a in active}
    assert replacement.id in active_ids
    assert original.id not in active_ids


# ---------------------------------------------------------------------------
# Provenance survives serialization
# ---------------------------------------------------------------------------

def test_provenance_survives_serialization_round_trip() -> None:
    original = create_artifact(
        engagement_id="eng-1",
        type="network.service",
        value={"host_ref": "h", "port": 445, "service_name": "smb"},
        target_ref="target-a",
        source_kind="action",
        source_id="nmap.discovery",
        source_execution_id="exec-1",
        confidence=0.9,
        sensitivity="sensitive",
        secret_ref=None,
        supersedes=None,
        expires_at=_future(),
        metadata={"parser": "nmap"},
    )
    dumped = original.model_dump()
    restored = HostArtifact.model_validate(dumped) if isinstance(original, HostArtifact) else ServiceArtifact.model_validate(dumped)
    assert restored.id == original.id
    assert restored.engagement_id == original.engagement_id
    assert restored.type == original.type
    assert restored.value == original.value
    assert restored.target_ref == original.target_ref
    assert restored.source_kind == original.source_kind
    assert restored.source_id == original.source_id
    assert restored.source_execution_id == original.source_execution_id
    assert restored.confidence == original.confidence
    assert restored.sensitivity == original.sensitivity
    assert restored.supersedes == original.supersedes
    assert restored.metadata == original.metadata


# ---------------------------------------------------------------------------
# Target scoping / cross-host prevention
# ---------------------------------------------------------------------------

def test_artifacts_for_target_filters_by_target_ref() -> None:
    a = create_artifact(engagement_id="e", type="network.host", value={"hostname": "h1"}, target_ref="target-a")
    b = create_artifact(engagement_id="e", type="network.service", value={"host_ref": "x", "port": 445, "service_name": "smb"}, target_ref="target-a")
    c = create_artifact(engagement_id="e", type="network.host", value={"hostname": "h2"}, target_ref="target-b")

    in_a = artifacts_for_target([a, b, c], "target-a")
    assert {x.id for x in in_a} == {a.id, b.id}

    in_b = artifacts_for_target([a, b, c], "target-b")
    assert {x.id for x in in_b} == {c.id}


def test_same_target_prevents_cross_host_match() -> None:
    host_a = create_artifact(engagement_id="e", type="network.host", value={"hostname": "h1"}, target_ref="target-a")
    svc_a = create_artifact(engagement_id="e", type="network.service", value={"host_ref": host_a.id, "port": 445, "service_name": "smb"}, target_ref="target-a")
    host_b = create_artifact(engagement_id="e", type="network.host", value={"hostname": "h2"}, target_ref="target-b")

    artifacts = [host_a, svc_a, host_b]
    requirement = ArtifactRequirement(type="network.service", same_target=True)

    matched, missing = match_required_artifacts(artifacts, [requirement], action_target_ref="target-a")
    assert svc_a.id in matched
    assert missing == []

    matched_b, missing_b = match_required_artifacts(artifacts, [requirement], action_target_ref="target-b")
    assert svc_a.id not in matched_b
    assert missing_b == ["network.service"]


def test_cross_target_allowed_when_same_target_false() -> None:
    host_a = create_artifact(engagement_id="e", type="network.host", value={"hostname": "h1"}, target_ref="target-a")
    host_b = create_artifact(engagement_id="e", type="network.host", value={"hostname": "h2"}, target_ref="target-b")

    artifacts = [host_a, host_b]
    requirement = ArtifactRequirement(type="network.host", same_target=False)

    matched, missing = match_required_artifacts(artifacts, [requirement], action_target_ref="target-b")
    assert host_a.id in matched  # cross-target explicitly allowed
    assert missing == []


# ---------------------------------------------------------------------------
# Remaining built-in artifact types (valid and invalid payloads)
# ---------------------------------------------------------------------------

def test_valid_domain_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="windows.domain",
        value={"name": "corp.local", "domain_controller": "dc01", "forest": "corp.local"},
        target_ref="target-a",
        sensitivity="internal",
    )
    from ambrosia.artifacts.models import DomainArtifact

    assert isinstance(artifact, DomainArtifact)
    assert artifact.value.name == "corp.local"
    assert artifact.value.domain_controller == "dc01"


def test_domain_name_required() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="windows.domain",
            value={"name": ""},
        )


def test_valid_host_role_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="windows.host_role",
        value={"host_ref": "host-1", "role": "member_server"},
        target_ref="target-a",
    )
    from ambrosia.artifacts.models import HostRoleArtifact

    assert isinstance(artifact, HostRoleArtifact)
    assert artifact.value.role == "member_server"


def test_valid_user_ref_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="identity.user_ref",
        value={"username": "svc_backup", "domain": "CORP", "sid": "S-1-5-21-0"},
        target_ref="target-a",
        sensitivity="sensitive",
    )
    from ambrosia.artifacts.models import UserRefArtifact

    assert isinstance(artifact, UserRefArtifact)
    assert artifact.value.username == "svc_backup"
    assert artifact.sensitivity == "sensitive"


def test_valid_evidence_ref_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="evidence.ref",
        value={
            "evidence_id": "ev-1",
            "path": "/data/evidence/ev-1.bin",
            "content_hash": "sha256:deadbeef",
            "media_type": "application/xml",
            "size_bytes": 1024,
        },
        target_ref="target-a",
    )
    from ambrosia.artifacts.models import EvidenceRefArtifact

    assert isinstance(artifact, EvidenceRefArtifact)
    assert artifact.value.content_hash == "sha256:deadbeef"
    assert artifact.value.size_bytes == 1024


def test_evidence_ref_negative_size_rejected() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="evidence.ref",
            value={"evidence_id": "ev-1", "size_bytes": -1},
        )


def test_valid_observation_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="observation",
        value={
            "id": "obs-1",
            "engagement_id": "eng-1",
            "target_ref": "target-a",
            "source_artifact_id": "svc-1",
            "title": "SMB port open",
            "evidence": {"port": 445, "protocol": "tcp"},
            "impact": "service exposure",
            "remediation": "close unnecessary port",
            "severity": "low",
        },
        target_ref="target-a",
    )
    from ambrosia.artifacts.models import ObservationArtifact

    assert isinstance(artifact, ObservationArtifact)
    assert artifact.value.title == "SMB port open"
    assert artifact.value.evidence == {"port": 445, "protocol": "tcp"}
    assert artifact.value.source_artifact_id == "svc-1"
    assert artifact.value.target_ref == "target-a"
    assert artifact.target_ref == "target-a"


def test_valid_finding_artifact() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="finding",
        value={
            "id": "find-1",
            "engagement_id": "eng-1",
            "target_ref": "target-a",
            "source_artifact_id": "obs-1",
            "title": "Weak protocol",
            "evidence": {"protocol": "SSLv3"},
            "impact": "information disclosure",
            "remediation": "disable SSLv3",
            "severity": "moderate",
            "status": "open",
        },
        target_ref="target-a",
    )
    from ambrosia.artifacts.models import FindingArtifact

    assert isinstance(artifact, FindingArtifact)
    assert artifact.value.status == "open"
    assert artifact.value.source_artifact_id == "obs-1"
    assert artifact.value.target_ref == "target-a"
    assert artifact.target_ref == "target-a"


def test_observation_artifact_secret_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="observation",
            value={
                "engagement_id": "eng-1",
                "title": "leak",
                "evidence": {"password": "hunter2"},
            },
        )


# ---------------------------------------------------------------------------
# Secret reference redaction: opaque handle only, never plaintext
# ---------------------------------------------------------------------------

def test_secret_ref_artifact_dump_contains_handle_not_value() -> None:
    artifact = create_artifact(
        engagement_id="eng-1",
        type="secret.ref",
        value={
            "secret_ref": "vault://creds/1",  # noqa: S105  # opaque secret handle, not a password
            "secret_type": "password",
            "label": "svc_acct",
        },  # noqa: S105
        target_ref="target-a",
        sensitivity="secret",
        secret_ref="vault://creds/1",  # noqa: S106  # opaque secret handle, not a password
    )
    dumped = artifact.model_dump()
    # Opaque handle is present (it is a reference, not the secret value).
    assert dumped["value"]["secret_ref"] == "vault://creds/1"  # noqa: S105  # opaque secret handle, not a password
    assert dumped["secret_ref"] == "vault://creds/1"  # noqa: S105  # opaque secret handle, not a password
    # No raw secret material anywhere in the serialized form.
    text = str(dumped)
    assert "hunter2" not in text
    assert "password" not in dumped["value"]
    # repr must not leak secret material either.
    assert "hunter2" not in repr(artifact)


def test_host_artifact_value_secret_key_rejected() -> None:
    with pytest.raises(ValidationError):
        create_artifact(
            engagement_id="eng-1",
            type="network.host",
            value={"hostname": "dc01", "token": "abc123"},
        )
