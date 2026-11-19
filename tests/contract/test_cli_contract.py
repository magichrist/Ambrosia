"""Contract tests: JSON output schema stability and exit codes."""

from __future__ import annotations

import json
from contextlib import nullcontext

import pytest
from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeExecutionRepository,
    FakeScopeRepository,
    FakeTargetRepository,
)
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
        artifact_repo=FakeArtifactRepository(),
        execution_repo=FakeExecutionRepository(),
        target_repo=FakeTargetRepository(),
    )


@pytest.fixture(autouse=True)
def _services() -> None:
    set_services(_make_services())


def _json(result) -> dict:
    assert result.exit_code == 0
    return json.loads(result.output)


def test_engagement_create_json_schema_stable() -> None:
    result = runner.invoke(
        app, ["engagement", "create", "schema-lab", "--output", "json"]
    )
    data = _json(result)
    assert set(data) == {"id", "name", "description", "status", "created_at", "updated_at", "scope_id"}
    assert isinstance(data["id"], str)
    assert data["name"] == "schema-lab"
    assert data["status"] == "active"


def test_actions_list_json_schema_stable() -> None:
    result = runner.invoke(app, ["actions", "list", "--output", "json"])
    data = _json(result)
    assert "actions" in data
    assert isinstance(data["actions"], list)
    if data["actions"]:
        action = data["actions"][0]
        assert set(action) == {
            "id",
            "version",
            "name",
            "description",
            "category",
            "tags",
            "platforms",
            "phase_refs",
            "executor_kind",
            "executor_executable",
            "effects",
            "risk",
            "approval_required",
            "timeout_seconds",
            "max_output_bytes",
            "dependencies",
            "scope_fields",
            "required_artifacts",
            "output_artifact_types",
            "parser_refs",
        }


def test_scope_show_json_schema_stable() -> None:
    result = runner.invoke(
        app, ["scope", "show", "--engagement", "eng-1", "--output", "json"]
    )
    data = _json(result)
    assert set(data) == {
        "id",
        "engagement_id",
        "include_hosts",
        "include_cidrs",
        "include_domains",
        "exclude_hosts",
        "exclude_cidrs",
        "allowed_ports",
        "expires_at",
        "max_concurrency",
        "max_requests_per_second",
        "allowed_effects",
        "require_approval_for",
    }


def test_json_is_stable_across_invocations() -> None:
    first = runner.invoke(app, ["engagement", "list", "--output", "json"])
    second = runner.invoke(app, ["engagement", "list", "--output", "json"])
    assert json.loads(first.output) == json.loads(second.output)


def test_exit_code_missing_preset() -> None:
    # No presets are registered in the fake service dirs, so running one is
    # a not-found (not a policy/execution) outcome.
    result = runner.invoke(app, ["preset", "run", "no-such-preset", "--engagement", "eng-1"])
    assert result.exit_code == 7


def test_exit_code_not_found() -> None:
    result = runner.invoke(app, ["actions", "info", "does-not-exist"])
    assert result.exit_code == 7


def test_error_payload_is_json() -> None:
    result = runner.invoke(app, ["engagement", "use", "nope", "--output", "json"])
    assert result.exit_code == 7
    data = json.loads(result.output)
    assert "error" in data
    assert data["error"]["code"] == "not_found"
    assert "message" in data["error"]
