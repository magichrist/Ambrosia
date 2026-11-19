# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the action registry (register, get, list, search, packs)."""

from __future__ import annotations

from pathlib import Path

from ambrosia.actions import register_builtins
from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.registry import (
    AvailabilityMatcher,
    ContextSnapshot,
    DuplicateActionError,
    DuplicatePackError,
    PackConflictError,
    Registry,
)

FIXTURE_PACK = "tests/fixtures/packs/test_pack.yaml"


def _make_action(action_id: str, category: str = "inventory") -> ActionDefinition:
    return ActionDefinition(
        id=action_id,
        version="1.0.0",
        name=action_id,
        description="A test action.",
        category=category,
        tags=["test"],
        platforms=[],
        executor=ExecutorReference(kind="native"),
        effects=["local_read"],
    )


def test_register_and_get() -> None:
    registry = Registry()
    action = _make_action("unit.test.alpha")
    registry.register_builtin(action)
    assert registry.get("unit.test.alpha") is action
    assert registry.has("unit.test.alpha")
    assert registry.get("unit.missing") is None


def test_duplicate_action_id_rejected() -> None:
    registry = Registry()
    registry.register_builtin(_make_action("unit.test.dup"))
    try:
        registry.register_builtin(_make_action("unit.test.dup"))
    except DuplicateActionError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("expected DuplicateActionError")


def test_builtins_register_without_execution(monkeypatch) -> None:
    executed = []

    class TracingHandler:
        async def execute(self, request, context):
            executed.append(request.action_id)
            return

    registry = Registry()
    action = _make_action("unit.test.noexec")
    registry.register_builtin(action, handler=TracingHandler())
    assert executed == [], "handler must not run during registration"
    assert registry.get_handler("unit.test.noexec") is not None


def test_list_search_and_filter() -> None:
    registry = Registry()
    registry.register_builtin(_make_action("unit.discovery.one", category="discovery"))
    registry.register_builtin(
        ActionDefinition(
            id="unit.discovery.two",
            version="1.0.0",
            name="Two",
            description="second",
            category="discovery",
            tags=["network"],
            platforms=["linux"],
            executor=ExecutorReference(kind="native"),
            effects=["network_observe"],
        )
    )
    registry.register_builtin(_make_action("unit.inventory.one", category="inventory"))

    all_actions = registry.list()
    assert [a.id for a in all_actions] == [
        "unit.discovery.one",
        "unit.discovery.two",
        "unit.inventory.one",
    ]

    by_category = registry.list(category="discovery")
    assert [a.id for a in by_category] == ["unit.discovery.one", "unit.discovery.two"]

    by_tag = registry.list(tag="network")
    assert [a.id for a in by_tag] == ["unit.discovery.two"]

    by_platform = registry.list(platform="linux")
    # Empty platforms means "no constraint / runs everywhere", so every action
    # is compatible with the linux filter.
    assert [a.id for a in by_platform] == [
        "unit.discovery.one",
        "unit.discovery.two",
        "unit.inventory.one",
    ]

    found = registry.search("inventory")
    assert [a.id for a in found] == ["unit.inventory.one"]

    found = registry.search("discovery")
    assert [a.id for a in found] == ["unit.discovery.one", "unit.discovery.two"]


def test_pack_load_from_fixture() -> None:
    import yaml

    registry = Registry()
    with Path(FIXTURE_PACK).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    result = registry.load_pack(data)
    assert result.ok
    assert result.actions_loaded == 3
    assert result.action_ids == ["test.scan.host", "test.read.config", "test.modify.file"]
    assert registry.get("test.scan.host") is not None
    assert registry.get("test.modify.file") is not None


def test_pack_enable_disable_hides_actions() -> None:
    registry = Registry()
    import yaml

    data = yaml.safe_load(Path(FIXTURE_PACK).open())
    registry.load_pack(data)
    assert len(registry.list()) == 3

    registry.disable_pack("test-pack")
    assert registry.list(enabled_only=True) == []
    # get still works (pack remains registered)
    assert registry.get("test.scan.host") is not None

    registry.enable_pack("test-pack")
    assert len(registry.list(enabled_only=True)) == 3


def test_duplicate_pack_rejected() -> None:
    registry = Registry()
    import yaml

    data = yaml.safe_load(Path(FIXTURE_PACK).open())
    registry.load_pack(data)
    try:
        registry.load_pack(data)
    except DuplicatePackError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected DuplicatePackError")


def test_pack_conflict_reported() -> None:
    registry = Registry()
    registry.register_builtin(_make_action("test.scan.host"))
    import yaml

    data = yaml.safe_load(Path(FIXTURE_PACK).open())
    try:
        registry.load_pack(data)
    except PackConflictError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected PackConflictError")


def test_pack_unload_removes_actions() -> None:
    registry = Registry()
    import yaml

    data = yaml.safe_load(Path(FIXTURE_PACK).open())
    registry.load_pack(data)
    removed = registry.unload_pack("test-pack")
    assert set(removed) == {"test.scan.host", "test.read.config", "test.modify.file"}
    assert registry.get("test.scan.host") is None


def test_matcher_sees_enabled_actions_only() -> None:
    registry = Registry()
    register_builtins(registry)
    import yaml

    data = yaml.safe_load(Path(FIXTURE_PACK).open())
    registry.load_pack(data)
    registry.disable_pack("test-pack")

    matcher = AvailabilityMatcher(registry)
    context = ContextSnapshot(engagement_id="e1")
    policy = __import__("ambrosia.registry.models", fromlist=["PolicySnapshot"]).PolicySnapshot()
    avail = matcher.evaluate("test.read.config", context, policy)
    assert avail.status == "not_applicable"
    assert "pack" in " ".join(avail.reasons).lower()
