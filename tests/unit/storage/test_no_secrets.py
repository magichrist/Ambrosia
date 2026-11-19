"""The storage layer must never store plaintext secret values."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord
from ambrosia.storage import Storage
from ambrosia.storage.models import (
    ApprovalRecordORM,
    ArtifactORM,
    EngagementORM,
    ExecutionEventORM,
    ExecutionORM,
    EvidenceMetadataORM,
    FindingORM,
    ScopeORM,
    TargetORM,
)
from ambrosia.storage.repositories import (
    ArtifactRepository,
    EngagementRepository,
    ExecutionRepository,
)

SECRET_LIKE_NAMES = {
    "password",
    "passwd",
    "secret",
    "token",
    "key",
    "credential",
    "hash",
    "apikey",
    "api_key",
    "private_key",
    "access_key",
}

# Opaque references and content hashes are metadata, not secret values.
# ``secret_ref`` stores an opaque secret handle and ``content_hash`` stores a
# SHA-256 of an evidence file's contents; neither holds a plaintext secret.
ALLOWED_REFERENCE_COLUMNS = {"secret_ref", "content_hash"}


def test_no_secret_like_columns_in_orm_tables() -> None:
    """ORM columns are metadata only; no column exists to hold secret values."""
    tables = {
        EngagementORM,
        ScopeORM,
        TargetORM,
        ArtifactORM,
        ExecutionORM,
        ExecutionEventORM,
        FindingORM,
        ApprovalRecordORM,
        EvidenceMetadataORM,
    }
    for table in tables:
        for column in table.__table__.columns:
            name = column.name.lower()
            if name in ALLOWED_REFERENCE_COLUMNS:
                continue
            for secret_token in SECRET_LIKE_NAMES:
                assert secret_token not in name, (
                    f"secret-like column {table.__tablename__}.{column.name}"
                )


def test_secret_material_is_rejected_before_persistence() -> None:
    """Artifact.value and execution input_summary are validated at the domain
    layer, so repository APIs never see or persist plaintext secrets. Only
    opaque ``secret_ref`` references are storable."""
    storage = Storage()
    with storage.session() as session:
        EngagementRepository(session).create(Engagement(id="e1", name="lab"))

        art_repo = ArtifactRepository(session)
        with pytest.raises(ValidationError):
            art_repo.add(
                Artifact(
                    id="a1",
                    engagement_id="e1",
                    type="network.host",
                    value={"password": "plaintext"},
                    source_kind="operator",
                )
            )
        assert art_repo.get("a1") is None

        exec_repo = ExecutionRepository(session)
        with pytest.raises(ValidationError):
            exec_repo.add(
                ExecutionRecord(
                    id="ex1",
                    engagement_id="e1",
                    status="draft",
                    input_summary={"token": "plaintext"},
                )
            )
        assert exec_repo.get("ex1") is None

        # Opaque references are fine and persist.
        art_repo.add(
            Artifact(
                id="a2",
                engagement_id="e1",
                type="secret.ref",
                value={"handle": "vault://ref"},
                source_kind="operator",
                secret_ref="vault://ref",
            )
        )
        assert art_repo.get("a2").secret_ref == "vault://ref"
