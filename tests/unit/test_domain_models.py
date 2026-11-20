"""Unit tests for expanded domain models: Target, Observation, Finding."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from ambrosia.domain.models import Finding, Observation, Target


def _future() -> datetime:
    return datetime.now() + timedelta(days=7)


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


def test_valid_target_ip() -> None:
    target = Target(engagement_id="eng-1", address="10.0.0.1", kind="ip")
    assert target.address == "10.0.0.1"
    assert target.kind == "ip"


def test_valid_target_domain() -> None:
    target = Target(engagement_id="eng-1", address="dc01.corp.local", kind="domain")
    assert target.address == "dc01.corp.local"
    assert target.kind == "domain"


def test_valid_target_hostname() -> None:
    target = Target(engagement_id="eng-1", address="dc01", kind="host")
    assert target.address == "dc01"
    assert target.kind == "host"


def test_target_invalid_ip_rejected() -> None:
    with pytest.raises(ValidationError):
        Target(engagement_id="eng-1", address="999.999.999.999", kind="ip")


def test_target_invalid_domain_rejected() -> None:
    with pytest.raises(ValidationError):
        Target(engagement_id="eng-1", address="not a domain", kind="domain")


def test_target_invalid_hostname_rejected() -> None:
    with pytest.raises(ValidationError):
        Target(engagement_id="eng-1", address="bad hostname!", kind="host")


def test_target_empty_address_rejected() -> None:
    with pytest.raises(ValidationError):
        Target(engagement_id="eng-1", address="   ", kind="host")


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def test_valid_observation() -> None:
    obs = Observation(
        engagement_id="eng-1",
        target_ref="target-a",
        source_artifact_id="artifact-1",
        title="SMB port open",
        evidence={"port": 445, "protocol": "tcp"},
        impact="service exposure",
        remediation="close unnecessary port",
        severity="low",
        confidence=0.8,
    )
    assert obs.title == "SMB port open"
    assert obs.target_ref == "target-a"
    assert obs.source_artifact_id == "artifact-1"
    assert obs.evidence == {"port": 445, "protocol": "tcp"}


def test_observation_secret_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation(
            engagement_id="eng-1",
            title="leak",
            evidence={"password": "hunter2"},
        )


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


def test_valid_finding() -> None:
    finding = Finding(
        engagement_id="eng-1",
        target_ref="target-a",
        source_artifact_id="artifact-1",
        title="Weak protocol",
        evidence={"protocol": "SSLv3"},
        impact="information disclosure",
        remediation="disable SSLv3",
        severity="moderate",
        status="open",
    )
    assert finding.status == "open"
    assert finding.severity == "moderate"
    assert finding.remediation == "disable SSLv3"


def test_finding_secret_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding(
            engagement_id="eng-1",
            title="leak",
            evidence={"token": "abc123"},
        )


def test_finding_round_trip_preserves_provenance() -> None:
    finding = Finding(
        engagement_id="eng-1",
        target_ref="target-a",
        source_artifact_id="artifact-1",
        title="X",
        evidence={"port": 445},
    )
    restored = Finding.model_validate(finding.model_dump())
    assert restored.id == finding.id
    assert restored.target_ref == finding.target_ref
    assert restored.source_artifact_id == finding.source_artifact_id
