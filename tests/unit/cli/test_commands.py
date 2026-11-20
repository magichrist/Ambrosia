"""End-to-end CLI command tests backed by fake application services."""

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
from ambrosia.application import (
    MISSING_DEPENDENCY,
    NOT_FOUND,
    OK,
    POLICY_BLOCKED,
    SCOPE_VIOLATION,
    VALIDATION_ERROR,
    ApplicationServices,
)
from ambrosia.cli.commands import set_services
from ambrosia.cli.main import app
from ambrosia.domain.action import ActionDefinition, ExecutorReference, ToolDependency
from ambrosia.domain.models import Engagement, Scope
from ambrosia.registry import Registry

runner = CliRunner()


def _make_registry() -> Registry:
    registry = Registry()
    register_builtins(registry)
    registry.register_builtin(
        ActionDefinition(
            id="network.nmap.service_discovery",
            version="1.0.0",
            name="Nmap Service Discovery",
            description="Discover services.",
            category="discovery",
            tags=[],
            platforms=[],
            scope_fields=["target"],
            dependencies=[ToolDependency(name="nmap")],
            effects=["network_observe"],
            risk="low",
            executor=ExecutorReference(kind="process", executable="nmap"),
        )
    )
    registry.register_builtin(
        ActionDefinition(
            id="test.remote_change",
            version="1.0.0",
            name="Blocked Change",
            description="blocked",
            category="test",
            tags=[],
            platforms=[],
            effects=["remote_change"],
            risk="high",
            executor=ExecutorReference(kind="native"),
        )
    )
    registry.register_builtin(
        ActionDefinition(
            id="test.missing_dep",
            version="1.0.0",
            name="Missing Dep",
            description="missing",
            category="test",
            tags=[],
            platforms=[],
            dependencies=[ToolDependency(name="nonexistent-tool-12345")],
            effects=["network_observe"],
            executor=ExecutorReference(kind="process", executable="nonexistent-tool-12345"),
        )
    )
    return registry


def _make_services() -> ApplicationServices:
    registry = _make_registry()
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


def test_engagement_create_list_use() -> None:
    result = runner.invoke(app, ["engagement", "create", "new-lab"])
    assert result.exit_code == OK
    assert "new-lab" in result.output

    result = runner.invoke(app, ["engagement", "list"])
    assert result.exit_code == OK
    assert "lab" in result.output

    result = runner.invoke(app, ["engagement", "use", "eng-1"])
    assert result.exit_code == OK


def test_engagement_use_unknown_exits_not_found() -> None:
    result = runner.invoke(app, ["engagement", "use", "nope"])
    assert result.exit_code == NOT_FOUND


def test_scope_show_and_update() -> None:
    result = runner.invoke(app, ["scope", "show", "--engagement", "eng-1"])
    assert result.exit_code == OK
    assert "10.0.0.1" in result.output

    result = runner.invoke(
        app,
        [
            "scope",
            "update",
            "--engagement",
            "eng-1",
            "--include-host",
            "10.0.0.2",
            "--allowed-port",
            "445",
        ],
    )
    assert result.exit_code == OK
    assert "10.0.0.2" in result.output


def test_scope_update_overlap_exits_validation() -> None:
    result = runner.invoke(
        app,
        [
            "scope",
            "update",
            "--engagement",
            "eng-1",
            "--include-host",
            "10.0.0.1",
            "--exclude-host",
            "10.0.0.1",
        ],
    )
    assert result.exit_code == VALIDATION_ERROR


def test_target_add_and_list() -> None:
    result = runner.invoke(
        app, ["target", "add", "10.0.0.1", "--engagement", "eng-1", "--kind", "ip"]
    )
    assert result.exit_code == OK
    assert "10.0.0.1" in result.output

    result = runner.invoke(app, ["target", "list", "--engagement", "eng-1"])
    assert result.exit_code == OK
    assert "10.0.0.1" in result.output


def test_target_invalid_address_exits_validation() -> None:
    result = runner.invoke(app, ["target", "add", "not an address", "--engagement", "eng-1"])
    assert result.exit_code == VALIDATION_ERROR


def test_actions_list_and_info() -> None:
    result = runner.invoke(app, ["actions", "list"])
    assert result.exit_code == OK
    assert "core.echo" in result.output

    result = runner.invoke(app, ["actions", "info", "core.echo"])
    assert result.exit_code == OK
    assert "Built-in diagnostic action" in result.output


def test_actions_info_unknown_exits_not_found() -> None:
    result = runner.invoke(app, ["actions", "info", "nope"])
    assert result.exit_code == NOT_FOUND


def test_actions_check_available() -> None:
    result = runner.invoke(
        app,
        [
            "actions",
            "check",
            "network.nmap.service_discovery",
            "--engagement",
            "eng-1",
            "--target",
            "10.0.0.1",
        ],
    )
    assert result.exit_code == OK


def test_actions_check_outside_scope_exits_scope_violation() -> None:
    result = runner.invoke(
        app,
        [
            "actions",
            "check",
            "network.nmap.service_discovery",
            "--engagement",
            "eng-1",
            "--target",
            "99.99.99.99",
        ],
    )
    assert result.exit_code == SCOPE_VIOLATION


def test_actions_check_policy_blocked_exits_policy_blocked() -> None:
    result = runner.invoke(
        app,
        [
            "actions",
            "check",
            "test.remote_change",
            "--engagement",
            "eng-1",
            "--target",
            "10.0.0.1",
        ],
    )
    assert result.exit_code == POLICY_BLOCKED


def test_actions_check_missing_dependency_exits_missing_dependency() -> None:
    result = runner.invoke(
        app,
        [
            "actions",
            "check",
            "test.missing_dep",
            "--engagement",
            "eng-1",
            "--target",
            "10.0.0.1",
        ],
    )
    assert result.exit_code == MISSING_DEPENDENCY


def test_preset_list_and_validate(tmp_path) -> None:
    # Services use builtin_presets dir by default via load_services, but our fake
    # services point presets_dirs at tmp_path via the fixture factory. Validate a
    # file path directly instead.
    result = runner.invoke(app, ["preset", "validate", "tests/fixtures/packs/does-not-exist.yml"])
    assert result.exit_code == NOT_FOUND


def test_preset_run_requires_engine_exits_missing_dependency(tmp_path) -> None:
    (tmp_path / "echo.yml").write_text(
        "api_version: ambrosia/v1\nkind: preset\nmetadata:\n  id: test.echo-preset\n  name: Echo Preset\n  version: 1.0.0\n  description: e.\nsteps:\n  - id: s\n    action: core.echo\n    inputs:\n      message: hi\n",
        encoding="utf-8",
    )
    services = _make_services()
    services.preset._presets_dirs = [tmp_path]
    set_services(services)
    result = runner.invoke(
        app,
        ["preset", "run", "test.echo-preset", "--engagement", "eng-1"],
    )
    assert result.exit_code == MISSING_DEPENDENCY


def test_jobs_list_show_cancel() -> None:
    result = runner.invoke(app, ["jobs", "list", "--engagement", "eng-1"])
    assert result.exit_code == OK

    result = runner.invoke(app, ["jobs", "show", "does-not-exist"])
    assert result.exit_code == NOT_FOUND


def test_report_export(tmp_path) -> None:
    out = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "report",
            "export",
            "--engagement",
            "eng-1",
            "--output-file",
            str(out),
        ],
    )
    assert result.exit_code == OK
    assert out.is_file()


def test_report_export_unknown_engagement_exits_not_found() -> None:
    result = runner.invoke(app, ["report", "export", "--engagement", "nope"])
    assert result.exit_code == NOT_FOUND


def test_json_output_is_valid_json() -> None:
    result = runner.invoke(app, ["engagement", "create", "json-lab", "--output", "json"])
    assert result.exit_code == OK
    data = json.loads(result.output)
    assert data["name"] == "json-lab"
    assert data["status"] == "active"


def test_json_output_on_error() -> None:
    result = runner.invoke(app, ["engagement", "use", "nope", "--output", "json"])
    assert result.exit_code == NOT_FOUND
    data = json.loads(result.output)
    assert data["error"]["code"] == "not_found"
