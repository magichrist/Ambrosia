"""Unit tests for the preset application service."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext

import pytest
from tests.conftest import (
    FakeArtifactRepository,
    FakeEngagementRepository,
    FakeScopeRepository,
)

from ambrosia.actions.builtins import register_builtins
from ambrosia.application.preset_service import PresetService
from ambrosia.domain.errors import (
    ConflictError,
    MissingDependencyError,
    ValidationError,
)
from ambrosia.domain.models import Engagement, Scope
from ambrosia.registry import Registry


def _make_registry() -> Registry:
    registry = Registry()
    register_builtins(registry)
    return registry


def _write_preset(tmp_path, name: str, content: str) -> str:
    path = tmp_path / f"{name}.yml"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _make_service(tmp_path, registry: Registry, user_presets_dir=None) -> PresetService:
    # Keep tests isolated from the real workspace presets directory.
    user_presets_dir = user_presets_dir or (tmp_path / "user-presets")
    return PresetService(
        session_scope=nullcontext,
        registry=registry,
        presets_dirs=[tmp_path],
        user_presets_dir=user_presets_dir,
        engagement_repo=FakeEngagementRepository(),
        scope_repo=FakeScopeRepository(),
        artifact_repo=FakeArtifactRepository(),
    )


def __import_artifact_repo():
    from tests.conftest import FakeArtifactRepository

    return FakeArtifactRepository()


VALID_PRESET = """api_version: ambrosia/v1
kind: preset
metadata:
  id: test.valid-preset
  name: Valid Preset
  version: 1.0.0
  description: A valid preset.
steps:
  - id: step-one
    action: core.echo
    inputs:
      message: hello
"""


def test_list_reports_loadable_presets(tmp_path) -> None:
    _write_preset(tmp_path, "valid", VALID_PRESET)
    registry = _make_registry()
    service = _make_service(tmp_path, registry)
    dtos = service.list()
    assert [d.id for d in dtos.presets] == ["test.valid-preset"]


BRANCH_PRESET = """api_version: ambrosia/v1
kind: preset
metadata:
  id: test.branch-preset
  name: Branch Preset
  version: 1.0.0
  description: A preset that uses engine-level condition branches.
steps:
  - id: discover
    action: core.echo
    inputs:
      message: hello
    outputs:
      services: { source: "{{ steps.discover.outputs.echo }}" }
  - id: suggest
    type: condition
    when:
      kind: input_present
      input: target
    then: [publish]
  - id: publish
    type: output
    outputs:
      next_actions: { source: "{{ steps.suggest.outputs.result }}" }
"""


def test_list_reports_branch_presets(tmp_path) -> None:
    """SHIPPED-PRESET REGRESSION: ``then``/``else`` are engine keys, not typos.

    Both bundled presets use condition branches. The service used to validate
    raw YAML against the strict domain model and reject them with
    ``extra_forbidden`` on ``steps.<n>.then``, so ``preset list``/validate/plan
    could never see a real shipped preset.
    """
    _write_preset(tmp_path, "branch", BRANCH_PRESET)
    service = _make_service(tmp_path, _make_registry())
    assert [d.id for d in service.list().presets] == ["test.branch-preset"]


def test_validate_accepts_branch_preset(tmp_path) -> None:
    path = _write_preset(tmp_path, "branch", BRANCH_PRESET)
    result = _make_service(tmp_path, _make_registry()).validate(path)
    assert result.valid is True
    assert result.errors == []
    assert result.step_count == 3


def test_plan_accepts_branch_preset(tmp_path) -> None:
    _write_preset(tmp_path, "branch", BRANCH_PRESET)
    plan = _make_service(tmp_path, _make_registry()).plan("test.branch-preset")
    # The service plan is a simplified, needs-only view; branch gating is
    # applied by the real PresetLoader at execution time. Assert the branch
    # steps are present rather than their topological position.
    assert {step.id for step in plan.steps} == {"discover", "suggest", "publish"}


def test_validate_accepts_valid_preset(tmp_path) -> None:
    path = _write_preset(tmp_path, "valid", VALID_PRESET)
    registry = _make_registry()
    service = _make_service(tmp_path, registry)
    result = service.validate(path)
    assert result.valid is True
    assert result.errors == []
    assert result.step_count == 1


def test_validate_rejects_invalid_yaml(tmp_path) -> None:
    path = _write_preset(tmp_path, "bad", "not: [valid: yaml")
    registry = _make_registry()
    service = _make_service(tmp_path, registry)
    with pytest.raises(ValidationError):
        service.validate(path)


def test_validate_rejects_unknown_action(tmp_path) -> None:
    content = VALID_PRESET.replace("core.echo", "does-not-exist")
    path = _write_preset(tmp_path, "bad-action", content)
    registry = _make_registry()
    service = _make_service(tmp_path, registry)
    result = service.validate(path)
    assert result.valid is False
    assert any("not registered" in e for e in result.errors)


def test_plan_produces_dry_run(tmp_path) -> None:
    _write_preset(tmp_path, "valid", VALID_PRESET)
    registry = _make_registry()
    service = _make_service(tmp_path, registry)
    plan = service.plan("test.valid-preset")
    assert plan.dry_run is True
    assert plan.steps[0].id == "step-one"
    assert plan.steps[0].status == "ready"


def test_plan_rejects_invalid_preset(tmp_path) -> None:
    content = VALID_PRESET.replace("test.valid-preset", "test.bad-preset").replace(
        "core.echo", "does-not-exist"
    )
    _write_preset(tmp_path, "bad", content)
    registry = _make_registry()
    service = _make_service(tmp_path, registry)
    with pytest.raises(ValidationError):
        service.plan("test.bad-preset")


def test_run_requires_engine(tmp_path) -> None:
    _write_preset(tmp_path, "valid", VALID_PRESET)
    registry = _make_registry()
    eng_repo = FakeEngagementRepository()
    scope_repo = FakeScopeRepository()
    eng_repo.create(Engagement(id="eng-1", name="lab", scope_id="scope-1"))
    scope_repo.create(Scope(id="scope-1", engagement_id="eng-1", include_hosts=["10.0.0.1"]))
    service = PresetService(
        session_scope=nullcontext,
        registry=registry,
        presets_dirs=[tmp_path],
        engine=None,
        engagement_repo=eng_repo,
        scope_repo=scope_repo,
        artifact_repo=FakeArtifactRepository(),
    )
    with pytest.raises(MissingDependencyError) as excinfo:
        asyncio.run(service.run("test.valid-preset", engagement_id="eng-1"))
    assert "engine" in str(excinfo.value).lower()


# ------------------------------------------------------------------ save


def test_save_forks_preset_into_user_directory(tmp_path) -> None:
    _write_preset(tmp_path, "source", BRANCH_PRESET)
    service = _make_service(tmp_path, _make_registry())

    saved = service.save("test.branch-preset", new_id="test.my-workflow", name="My Workflow")

    assert saved.id == "test.my-workflow"
    assert saved.name == "My Workflow"
    assert saved.step_count == 3
    assert (tmp_path / "user-presets" / "test.my-workflow.yaml").is_file()
    # The saved copy is immediately discoverable and keeps branch keys.
    assert "test.my-workflow" in [p.id for p in service.list().presets]
    body = (tmp_path / "user-presets" / "test.my-workflow.yaml").read_text()
    assert "then" in body
    # The original is untouched.
    assert "test.branch-preset" in [p.id for p in service.list().presets]


def test_save_rejects_existing_id(tmp_path) -> None:
    _write_preset(tmp_path, "source", BRANCH_PRESET)
    service = _make_service(tmp_path, _make_registry())

    with pytest.raises(ConflictError):
        service.save("test.branch-preset", new_id="test.branch-preset")


def test_save_rejects_invalid_id(tmp_path) -> None:
    _write_preset(tmp_path, "source", BRANCH_PRESET)
    service = _make_service(tmp_path, _make_registry())

    with pytest.raises(ValidationError):
        service.save("test.branch-preset", new_id="../escaped")


def test_save_rejects_invalid_source(tmp_path) -> None:
    path = _write_preset(tmp_path, "bad", VALID_PRESET.replace("core.echo", "no-such-action"))
    service = _make_service(tmp_path, _make_registry())

    with pytest.raises(ValidationError):
        service.save(path)
