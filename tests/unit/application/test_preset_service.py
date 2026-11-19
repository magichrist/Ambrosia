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


def _make_service(tmp_path, registry: Registry) -> PresetService:
    return PresetService(
        session_scope=nullcontext,
        registry=registry,
        presets_dirs=[tmp_path],
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
    content = (
        VALID_PRESET.replace("test.valid-preset", "test.bad-preset")
        .replace("core.echo", "does-not-exist")
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
