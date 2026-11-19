"""Repository CRUD, relationship, isolation, and boundary tests."""

from __future__ import annotations

import pytest

from ambrosia.domain.models import (
    Artifact,
    Engagement,
    ExecutionRecord,
    Scope,
)
from ambrosia.domain.protocols import (
    ArtifactRepository as ArtifactProto,
)
from ambrosia.domain.protocols import (
    EngagementRepository as EngagementProto,
)
from ambrosia.domain.protocols import (
    ExecutionRepository as ExecutionProto,
)
from ambrosia.domain.protocols import (
    ScopeRepository as ScopeProto,
)
from ambrosia.storage import (
    ApprovalRecordRepository,
    ArtifactRepository,
    EngagementRepository,
    EvidenceRepository,
    ExecutionRepository,
    FindingRepository,
    ScopeRepository,
    TargetRepository,
)
from ambrosia.storage.models import EngagementORM, ScopeORM


def test_engagement_crud(session) -> None:
    repo = EngagementRepository(session)
    created = repo.create(
        Engagement(id="e1", name="lab", description="d", status="active")
    )
    assert created.id == "e1"
    assert created.name == "lab"
    assert created.status == "active"
    assert isinstance(created, Engagement)  # domain model, not an ORM instance
    assert not isinstance(created, EngagementORM)

    got = repo.get("e1")
    assert got is not None and got.name == "lab"
    assert repo.get("missing") is None

    all_engagements = repo.list()
    assert len(all_engagements) == 1

    got.status = "paused"
    repo.update(got)
    assert repo.get("e1").status == "paused"

    with pytest.raises(Exception):
        repo.update(Engagement(id="nope", name="x"))


def test_scope_one_per_engagement(session) -> None:
    EngagementRepository(session).create(Engagement(id="e1", name="one"))
    scope_repo = ScopeRepository(session)
    scope = Scope(
        id="s1",
        engagement_id="e1",
        include_hosts=["192.0.2.10"],
        include_cidrs=["10.0.0.0/8"],
        include_domains=["example.internal"],
        exclude_hosts=["192.0.2.99"],
        allowed_effects={"local_read", "network_observe"},
        require_approval_for={"remote_change"},
    )
    created = scope_repo.create(scope)
    assert created.id == "s1"
    assert isinstance(created, Scope)
    assert not isinstance(created, ScopeORM)

    got = scope_repo.get_for_engagement("e1")
    assert got is not None
    assert got.include_hosts == ["192.0.2.10"]
    assert got.include_cidrs == ["10.0.0.0/8"]
    assert got.allowed_effects == {"local_read", "network_observe"}
    assert got.require_approval_for == {"remote_change"}
    assert scope_repo.get_for_engagement("other") is None

    created.max_concurrency = 5
    scope_repo.update(created)
    assert scope_repo.get("s1").max_concurrency == 5


def test_artifact_crud_and_target_binding(session) -> None:
    EngagementRepository(session).create(Engagement(id="e1", name="one"))
    EngagementRepository(session).create(Engagement(id="e2", name="two"))
    art_repo = ArtifactRepository(session)
    art_repo.add(
        Artifact(
            id="a1",
            engagement_id="e1",
            type="network.host",
            value={"ip": "192.0.2.10"},
            source_kind="operator",
            target_ref="192.0.2.10",
        )
    )
    art_repo.add(
        Artifact(
            id="a2",
            engagement_id="e1",
            type="network.service",
            value={"port": 445},
            source_kind="action",
            target_ref="192.0.2.10",
        )
    )
    a3 = art_repo.add(
        Artifact(
            id="a3",
            engagement_id="e2",
            type="network.host",
            value={"ip": "10.0.0.1"},
            source_kind="operator",
            target_ref="10.0.0.1",
        )
    )

    assert art_repo.get("a1").type == "network.host"
    assert art_repo.get("a1").target_ref == "192.0.2.10"
    assert len(art_repo.list_for_engagement("e1")) == 2
    assert len(art_repo.list_for_engagement("e2")) == 1
    by_target = art_repo.list_by_target("192.0.2.10")
    assert {art.id for art in by_target} == {"a1", "a2"}
    assert art_repo.list_by_target("10.0.0.1") == [a3]
    assert art_repo.get("missing") is None


def test_execution_and_events(session) -> None:
    EngagementRepository(session).create(Engagement(id="e1", name="one"))
    exec_repo = ExecutionRepository(session)
    ex = exec_repo.add(
        ExecutionRecord(
            id="ex1",
            engagement_id="e1",
            action_id="net.discovery",
            status="running",
            target_refs=["192.0.2.10"],
            input_summary={"ports": "445"},
            output_artifact_ids=["a1"],
        )
    )
    assert ex.status == "running"
    exec_repo.add_event("ex1", "ProgressEvent", {"message": "started"}, 0)
    exec_repo.add_event("ex1", "LogEvent", {"level": "info"}, 1)
    events = exec_repo.list_events("ex1")
    assert [e["kind"] for e in events] == ["ProgressEvent", "LogEvent"]
    assert events[0]["sequence"] == 0

    ex.status = "succeeded"
    exec_repo.update(ex)
    assert exec_repo.get("ex1").status == "succeeded"
    assert exec_repo.get("nope") is None
    assert len(exec_repo.list_for_engagement("e1")) == 1


def test_engagement_isolation(session) -> None:
    repo = EngagementRepository(session)
    repo.create(Engagement(id="e1", name="one"))
    repo.create(Engagement(id="e2", name="two"))

    art_repo = ArtifactRepository(session)
    art_repo.add(
        Artifact(id="a1", engagement_id="e1", type="network.host", value={}, source_kind="operator")
    )
    art_repo.add(
        Artifact(id="a2", engagement_id="e2", type="network.host", value={}, source_kind="operator")
    )

    assert {a.id for a in art_repo.list_for_engagement("e1")} == {"a1"}
    assert {a.id for a in art_repo.list_for_engagement("e2")} == {"a2"}
    assert len(repo.list()) == 2


def test_target_finding_approval_evidence_repositories(session) -> None:
    EngagementRepository(session).create(Engagement(id="e1", name="one"))
    target_repo = TargetRepository(session)
    t = target_repo.create(
        engagement_id="e1", address="192.0.2.10", target_type="host", hostname="host.internal"
    )
    assert target_repo.get(t.id).address == "192.0.2.10"
    assert len(target_repo.list_for_engagement("e1")) == 1

    finding_repo = FindingRepository(session)
    f = finding_repo.create(
        engagement_id="e1", title="Weak config", severity="low", target_ref="192.0.2.10"
    )
    assert finding_repo.get(f.id).title == "Weak config"
    assert len(finding_repo.list_for_engagement("e1")) == 1

    approval_repo = ApprovalRecordRepository(session)
    ap = approval_repo.create(
        engagement_id="e1", effect="remote_change", decision="pending"
    )
    assert approval_repo.get(ap.id).decision == "pending"
    approval_repo.update_decision(ap.id, decision="approved", decided_by="operator")
    assert approval_repo.get(ap.id).decision == "approved"
    assert len(approval_repo.list_for_engagement("e1")) == 1

    evidence_repo = EvidenceRepository(session)
    assert evidence_repo.list_for_engagement("e1") == []
    assert evidence_repo.get("nope") is None


def test_no_orm_instances_escape_repositories(session) -> None:
    """Repository APIs return domain models, never ORM instances."""
    repo = EngagementRepository(session)
    engagement = repo.create(Engagement(id="e1", name="leak-check"))
    assert type(engagement) is Engagement
    assert type(repo.get("e1")) is Engagement
    assert all(type(x) is Engagement for x in repo.list())

    scope_repo = ScopeRepository(session)
    scope = scope_repo.create(
        Scope(id="s1", engagement_id="e1", include_hosts=["192.0.2.10"])
    )
    assert type(scope) is Scope
    assert type(scope_repo.get_for_engagement("e1")) is Scope

    art_repo = ArtifactRepository(session)
    art = art_repo.add(
        Artifact(
            id="a1", engagement_id="e1", type="network.host", value={}, source_kind="operator"
        )
    )
    assert type(art) is Artifact
    assert type(art_repo.get("a1")) is Artifact
    assert all(type(x) is Artifact for x in art_repo.list_for_engagement("e1"))

    exec_repo = ExecutionRepository(session)
    ex = exec_repo.add(
        ExecutionRecord(id="ex1", engagement_id="e1", status="draft")
    )
    assert type(ex) is ExecutionRecord
    assert type(exec_repo.get("ex1")) is ExecutionRecord


def test_repositories_satisfy_shared_protocols(session) -> None:
    assert isinstance(EngagementRepository(session), EngagementProto)
    assert isinstance(ScopeRepository(session), ScopeProto)
    assert isinstance(ArtifactRepository(session), ArtifactProto)
    assert isinstance(ExecutionRepository(session), ExecutionProto)


@pytest.fixture
def session():
    """Transactional session over an in-memory DB, rolled back after each test."""
    from ambrosia.storage import Storage

    storage = Storage()
    with storage.session() as db_session:
        yield db_session
