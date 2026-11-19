# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for Windows assessment pack registration and action metadata.

Verifies the pack loads and validates, that action metadata declares effects,
target scope fields, and tool dependencies, and that registration never
executes an assessment tool.
"""

from __future__ import annotations

from ambrosia.packs.windows_assessment import (
    PACK_ID,
    actions,
    load_manifest,
    register_pack,
)
from ambrosia.registry import Registry
from ambrosia.registry.models import PackManifest
from ambrosia.registry.validation import validate_action_definition


def test_load_manifest_validates() -> None:
    manifest = load_manifest()
    assert isinstance(manifest, PackManifest)
    assert manifest.metadata.id == PACK_ID
    assert manifest.metadata.version == "1.0.0"
    assert len(manifest.actions) == 6
    action_ids = {a.id for a in manifest.actions}
    assert action_ids == {
        "network.nmap.service_discovery",
        "windows.smb.configuration_audit",
        "windows.ldap.domain_inventory",
        "windows.http.method_observation",
        "windows.rdp.exposure_observation",
        "windows.winrm.exposure_observation",
    }


def test_register_pack_registers_all_actions_with_handlers() -> None:
    registry = Registry()
    result = register_pack(registry)

    assert result.actions_loaded == 6
    assert result.ok
    for action in actions.ALL_ACTIONS:
        assert registry.has(action.id)
        assert registry.get(action.id) is not None
        assert registry.get_handler(action.id) is not None
        assert registry.action_pack_id(action.id) == PACK_ID


def test_action_metadata_declares_effects_target_fields_and_dependencies() -> None:
    registry = Registry()
    register_pack(registry)

    for action in actions.ALL_ACTIONS:
        # Read-only discovery only.
        assert action.effects == ["network_observe"]
        assert action.approval_required is False
        assert action.risk in {"info", "low"}
        # Every network action declares its target scope field.
        assert action.scope_fields == ["target"]
        # Machine-readable output parser reference.
        assert action.parser_refs == ["nmap_xml"]
        # Bounded Nmap dependency declared as metadata (never executed at
        # registration; availability is a matcher PATH check).
        assert len(action.dependencies) == 1
        dep = action.dependencies[0]
        assert dep.name == "nmap"
        assert dep.check_command == ["nmap", "--version"]
        # Process executor backed by the allowlisted nmap executable.
        assert action.executor.kind == "process"
        assert action.executor.executable == "nmap"
        # Validated definition (no validation errors).
        assert validate_action_definition(action).ok


def test_registration_does_not_execute_any_tool() -> None:
    from ambrosia.executors import FakeExecutor

    fake = FakeExecutor()
    registry = Registry()
    register_pack(registry, executor=fake)

    # Registration is a metadata operation: the executor must not have been
    # invoked and no assessment has run.
    assert fake.calls == []
    for action in actions.ALL_ACTIONS:
        assert registry.has(action.id)


def test_no_target_modifying_behavior() -> None:
    registry = Registry()
    register_pack(registry)
    for action in actions.ALL_ACTIONS:
        for effect in action.effects:
            assert effect not in {
                "local_write",
                "remote_change",
                "credential_access",
                "authentication",
            }
