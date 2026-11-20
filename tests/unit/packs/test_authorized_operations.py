# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the opt-in authorized operations pack.

No external tool is installed or executed: all runs use FakeExecutor.
"""

from __future__ import annotations

import pytest

from ambrosia.domain.errors import PolicyBlockedError
from ambrosia.domain.protocols import ActionExecutionContext, ActionRequest
from ambrosia.executors.fake import FakeExecutor
from ambrosia.packs.authorized_operations import (
    PACK_ID,
    actions,
    argv,
    load_manifest,
    register_authorized_operations,
)
from ambrosia.packs.authorized_operations.handlers import AuthorizedToolHandler
from ambrosia.registry import Registry

_CONTEXT = ActionExecutionContext(engagement_id="eng-1")


def _request(action_id: str, **inputs: object) -> ActionRequest:
    return ActionRequest(execution_id="exec-1", action_id=action_id, inputs=dict(inputs))


async def _collect(handler: AuthorizedToolHandler, request: ActionRequest) -> list:
    return [event async for event in handler.execute(request, _CONTEXT)]


# --------------------------------------------------------------------------- manifest / registration


def test_manifest_loads_without_side_effects() -> None:
    manifest = load_manifest()
    assert manifest.metadata.id == PACK_ID
    assert len(manifest.actions) == 7


def test_registration_requires_explicit_call() -> None:
    registry = Registry()
    assert not registry.has("windows.credentials.secretsdump")
    result = register_authorized_operations(registry, executor=FakeExecutor())
    assert result.actions_loaded == 7
    assert registry.action_pack_id("windows.credentials.secretsdump") == PACK_ID
    assert registry.get_handler("windows.smb.netexec") is not None


def test_all_actions_are_high_impact_and_scoped() -> None:
    for definition in actions.ALL_ACTIONS:
        assert definition.effects
        assert any(
            effect in {"credential_access", "remote_change", "authentication"}
            for effect in definition.effects
        ), definition.id
        assert definition.approval_required is True
        assert "authorization_reference" in definition.input_schema["required"]


def test_target_actions_declare_scope_fields() -> None:
    for definition in actions.ALL_ACTIONS:
        if definition.id == "windows.credentials.samdump2":
            continue  # offline hive action has no network target
        assert "target" in definition.scope_fields, definition.id


# --------------------------------------------------------------------------- argv builders


@pytest.mark.parametrize(
    ("builder", "inputs", "expected"),
    [
        (
            argv.build_secretsdump_argv,
            {"target": "10.0.0.10"},
            ["-no-pass", "10.0.0.10"],
        ),
        (
            argv.build_samdump2_argv,
            {"system_hive": "/ev/SYSTEM", "sam_hive": "/ev/SAM"},
            ["/ev/SYSTEM", "/ev/SAM"],
        ),
        (
            argv.build_netexec_argv,
            {"target": "10.0.0.10", "protocol": "smb", "username": "u", "password": "p"},
            ["smb", "10.0.0.10", "-u", "u", "-p", "p"],
        ),
        (
            argv.build_netexec_exec_argv,
            {"target": "10.0.0.10", "username": "u", "command": "whoami"},
            ["smb", "10.0.0.10", "-u", "u", "-x", "whoami"],
        ),
        (
            argv.build_psexec_argv,
            {"target": "10.0.0.10", "username": "u", "password": "p", "command": "whoami"},
            ["u:p@10.0.0.10", "whoami"],
        ),
        (
            argv.build_domain_enumeration_argv,
            {"target": "dc01.corp.local", "domain": "corp.local"},
            ["dc01.corp.local", "-all", "corp.local"],
        ),
        (
            argv.build_ntlm_relay_argv,
            {"target": "10.0.0.10"},
            ["-t", "smb://10.0.0.10", "-smb2support"],
        ),
    ],
)
def test_argv_builders(builder, inputs, expected) -> None:
    assert builder(inputs) == expected


def test_argv_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        argv.build_secretsdump_argv({})
    with pytest.raises(ValueError):
        argv.build_netexec_argv({"target": "10.0.0.10", "protocol": "ftp"})


def test_authorization_input_is_not_forwarded_to_argv() -> None:
    built = argv.build_secretsdump_argv({"target": "10.0.0.10", "authorization_reference": "ROE-1"})
    assert "ROE-1" not in built


# --------------------------------------------------------------------------- handler gating


@pytest.mark.asyncio
async def test_handler_refuses_run_without_authorization() -> None:
    fake = FakeExecutor()
    handler = AuthorizedToolHandler(fake, actions.SECRETSDUMP)

    events = await _collect(
        handler, _request("windows.credentials.secretsdump", target="10.0.0.10")
    )

    assert events[-1].kind == "FailedEvent"
    assert events[-1].payload["code"] == "authorization_or_input_error"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_handler_runs_with_authorization_and_hides_output_by_default() -> None:
    fake = FakeExecutor(output="hash:AAAA")
    handler = AuthorizedToolHandler(fake, actions.SECRETSDUMP)

    events = await _collect(
        handler,
        _request(
            "windows.credentials.secretsdump",
            target="10.0.0.10",
            authorization_reference="ROE-42",
        ),
    )

    assert fake.calls, "executor should have run"
    assert fake.last_argv() == ["-no-pass", "10.0.0.10"]
    assert not any(e.kind == "OutputChunkEvent" for e in events)
    completed = next(e for e in events if e.kind == "CompletedEvent")
    assert completed.payload["summary"]["output_retained"] is False
    assert completed.payload["summary"]["authorization_reference"] == "ROE-42"


@pytest.mark.asyncio
async def test_handler_retains_output_when_explicitly_requested() -> None:
    fake = FakeExecutor()
    handler = AuthorizedToolHandler(fake, actions.NETEXEC)

    events = await _collect(
        handler,
        _request(
            "windows.smb.netexec",
            target="10.0.0.10",
            protocol="smb",
            authorization_reference="ROE-42",
            show_output=True,
        ),
    )

    output = [e for e in events if e.kind == "OutputChunkEvent"]
    assert len(output) == 1
    completed = next(e for e in events if e.kind == "CompletedEvent")
    assert completed.payload["summary"]["output_retained"] is True


def test_authorization_service_requires_reference() -> None:
    from ambrosia.policy.authorization import AuthorizationService

    service = AuthorizationService()
    with pytest.raises(PolicyBlockedError):
        service.require_reference(actions.SECRETSDUMP, None)
    grant = service.require_reference(actions.SECRETSDUMP, "ROE-7")
    assert grant is not None and grant.reference == "ROE-7"
    with pytest.raises(PolicyBlockedError):
        service.require_reference(actions.SECRETSDUMP, "   ")
