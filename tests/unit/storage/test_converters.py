"""Typed domain model serialization through the ORM boundary."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord, Scope
from ambrosia.storage import Storage
from ambrosia.storage.converters import (
    artifact_from_orm,
    artifact_to_orm,
    engagement_from_orm,
    engagement_to_orm,
    execution_from_orm,
    execution_to_orm,
    scope_from_orm,
    scope_to_orm,
)
from ambrosia.storage.models import (
    ArtifactORM,
    EngagementORM,
    ExecutionORM,
)
from ambrosia.storage.repositories import ArtifactRepository, EngagementRepository


def _dt() -> datetime:
    return datetime(2026, 2, 3, 4, 5, 6)


def test_engagement_serialization_round_trip() -> None:
    engagement = Engagement(
        id="e1", name="lab", description="d", status="paused",
        created_at=_dt(), updated_at=_dt(), scope_id="s1",
    )
    orm = engagement_to_orm(engagement)
    assert isinstance(orm, EngagementORM)
    assert orm.created_at.tzinfo is not None  # stored as aware UTC
    back = engagement_from_orm(orm)
    assert back == engagement
    assert back.created_at == _dt()


def test_scope_sets_round_trip_as_lists() -> None:
    scope = Scope(
        id="s1", engagement_id="e1",
        include_hosts=["192.0.2.10"],
        exclude_cidrs=["10.0.0.0/8"],
        allowed_effects={"local_read"},
        require_approval_for={"remote_change", "authentication"},
    )
    orm = scope_to_orm(scope)
    assert isinstance(orm.allowed_effects, list)
    assert isinstance(orm.require_approval_for, list)
    back = scope_from_orm(orm)
    assert back == scope
    assert back.allowed_effects == {"local_read"}
    assert back.require_approval_for == {"remote_change", "authentication"}


def test_artifact_json_fields_round_trip() -> None:
    artifact = Artifact(
        id="a1", engagement_id="e1", type="network.host",
        value={"ip": "192.0.2.10", "ports": [22, 445]},
        source_kind="action", source_id="act-1", source_execution_id="ex-1",
        target_ref="192.0.2.10", created_at=_dt(), confidence=0.9,
        sensitivity="sensitive", secret_ref="vault://s/1",
        scope_binding={"target": "192.0.2.10"}, supersedes="a0",
        expires_at=_dt(), metadata={"tool": "nmap"},
    )
    orm = artifact_to_orm(artifact)
    assert isinstance(orm, ArtifactORM)
    assert orm.created_at.tzinfo is not None
    back = artifact_from_orm(orm)
    assert back == artifact
    assert back.value == {"ip": "192.0.2.10", "ports": [22, 445]}
    assert back.metadata == {"tool": "nmap"}
    assert back.scope_binding == {"target": "192.0.2.10"}


def test_execution_json_fields_round_trip() -> None:
    execution = ExecutionRecord(
        id="ex1", engagement_id="e1", action_id="net.discovery",
        preset_id="preset-1", status="running", started_at=_dt(),
        target_refs=["192.0.2.10"], input_summary={"ports": "445"},
        output_artifact_ids=["a1"], error_code=None, error_message=None,
        initiated_by="operator",
    )
    orm = execution_to_orm(execution)
    assert isinstance(orm, ExecutionORM)
    back = execution_from_orm(orm)
    assert back == execution
    assert back.target_refs == ["192.0.2.10"]
    assert back.input_summary == {"ports": "445"}


def test_artifact_rejects_secret_material_in_value() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            id="a1", engagement_id="e1", type="network.host",
            value={"password": "hunter2"}, source_kind="operator",
        )


def test_execution_rejects_secret_material_in_input_summary() -> None:
    with pytest.raises(ValidationError):
        ExecutionRecord(
            id="ex1", engagement_id="e1", status="draft",
            input_summary={"token": "abc123"},
        )


def test_storage_never_receives_secret_values() -> None:
    """End-to-end: domain validation blocks secrets before the ORM boundary."""
    storage = Storage()
    with storage.session() as session:
        EngagementRepository(session).create(Engagement(id="e1", name="lab"))
        art_repo = ArtifactRepository(session)
        with pytest.raises(ValidationError):
            art_repo.add(
                Artifact(
                    id="a1", engagement_id="e1", type="network.host",
                    value={"password": "hunter2"}, source_kind="operator",
                )
            )
        # The failed add must not leave partial state.
        assert art_repo.get("a1") is None



