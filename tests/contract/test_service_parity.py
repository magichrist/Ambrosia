"""Contract test: the CLI and TUI invoke the same application service path.

Both interfaces delegate to :class:`ambrosia.application.ApplicationServices`;
the CLI never contains business logic. We spy on service methods to confirm
each CLI command routes through the shared service layer.
"""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import patch

import pytest
from tests.conftest import FakeEngagementRepository, FakeScopeRepository
from typer.testing import CliRunner

from ambrosia.actions.builtins import register_builtins
from ambrosia.application import ApplicationServices
from ambrosia.cli.commands import set_services
from ambrosia.cli.main import app
from ambrosia.domain.models import Engagement, Scope
from ambrosia.registry import Registry

runner = CliRunner()


def _make_services() -> ApplicationServices:
    registry = Registry()
    register_builtins(registry)
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab", scope_id="scope-1"))
    scope_repo.create(
        Scope(
            id="scope-1",
            engagement_id="eng-1",
            include_hosts=["10.0.0.1"],
            allowed_effects={"local_read", "network_observe"},
        )
    )
    return ApplicationServices(
        session_scope=nullcontext,
        registry=registry,
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
    )


@pytest.fixture(autouse=True)
def _services() -> None:
    set_services(_make_services())


def test_engagement_create_routes_through_service() -> None:
    from ambrosia.application.engagement_service import EngagementDTO, EngagementService

    dto = EngagementDTO(
        id="eng-1",
        name="spy-lab",
        description=None,
        status="active",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        scope_id="scope-1",
    )
    with patch.object(EngagementService, "create", return_value=dto) as spy:
        result = runner.invoke(app, ["engagement", "create", "spy-lab"])
        assert result.exit_code == 0
        spy.assert_called_once()
        assert spy.call_args.kwargs.get("name") == "spy-lab"


def test_actions_check_routes_through_service() -> None:
    from ambrosia.application.action_service import ActionCheckDTO, ActionService

    dto = ActionCheckDTO(
        action_id="core.echo",
        status="available",
        reasons=[],
        missing_inputs=[],
        matched_artifact_ids=[],
        required_approval=False,
        allowed=True,
    )
    with patch.object(ActionService, "check", return_value=dto) as spy:
        result = runner.invoke(
            app,
            ["actions", "check", "core.echo", "--engagement", "eng-1"],
        )
        assert result.exit_code == 0
        spy.assert_called_once()
        # action_id is passed positionally to the mocked method (self is not
        # prepended when patching a class attribute).
        assert spy.call_args.args[0] == "core.echo"
