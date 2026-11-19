"""Contract tests: storage repositories implement the shared domain protocols."""

from __future__ import annotations

from ambrosia.domain.models import Artifact, Engagement, ExecutionRecord, Scope
from ambrosia.domain.protocols import (
    ArtifactRepository,
    EngagementRepository,
    ExecutionRepository,
    ScopeRepository,
)
from ambrosia.storage import (
    ArtifactRepository as OrmArtifactRepository,
)
from ambrosia.storage import (
    EngagementRepository as OrmEngagementRepository,
)
from ambrosia.storage import (
    ExecutionRepository as OrmExecutionRepository,
)
from ambrosia.storage import (
    ScopeRepository as OrmScopeRepository,
)
from ambrosia.storage import Storage


def test_repositories_implement_shared_protocols() -> None:
    storage = Storage()  # in-memory DB
    with storage.session() as session:
        assert isinstance(OrmEngagementRepository(session), EngagementRepository)
        assert isinstance(OrmScopeRepository(session), ScopeRepository)
        assert isinstance(OrmArtifactRepository(session), ArtifactRepository)
        assert isinstance(OrmExecutionRepository(session), ExecutionRepository)


def test_repositories_return_domain_models_not_orm() -> None:
    storage = Storage()
    with storage.session() as session:
        engagement_repo = OrmEngagementRepository(session)
        scope_repo = OrmScopeRepository(session)
        artifact_repo = OrmArtifactRepository(session)
        execution_repo = OrmExecutionRepository(session)

        engagement = engagement_repo.create(Engagement(id="e1", name="contract"))
        assert type(engagement) is Engagement

        scope = scope_repo.create(Scope(id="s1", engagement_id="e1"))
        assert type(scope) is Scope

        artifact = artifact_repo.add(
            Artifact(id="a1", engagement_id="e1", type="network.host", value={}, source_kind="operator")
        )
        assert type(artifact) is Artifact

        execution = execution_repo.add(
            ExecutionRecord(id="x1", engagement_id="e1", status="draft")
        )
        assert type(execution) is ExecutionRecord

        assert type(engagement_repo.get("e1")) is Engagement
        assert type(scope_repo.get_for_engagement("e1")) is Scope
        assert type(artifact_repo.get("a1")) is Artifact
        assert type(execution_repo.get("x1")) is ExecutionRecord
        assert all(type(x) is Engagement for x in engagement_repo.list())
        assert all(type(x) is Artifact for x in artifact_repo.list_for_engagement("e1"))
        assert all(type(x) is ExecutionRecord for x in execution_repo.list_for_engagement("e1"))
