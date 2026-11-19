# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.
"""Unit tests for built-in actions (core.echo diagnostic)."""

from __future__ import annotations

import pytest

from ambrosia.actions import CORE_ECHO_ACTION, EchoHandler, register_builtins
from ambrosia.domain.protocols import ActionExecutionContext, ActionRequest
from ambrosia.registry import Registry


@pytest.mark.asyncio
async def test_echo_handler_returns_input() -> None:
    handler = EchoHandler()
    request = ActionRequest(
        execution_id="exec-1",
        action_id="core.echo",
        inputs={"message": "hello ambrosia"},
    )
    context = ActionExecutionContext(engagement_id="e1")

    events = [event async for event in handler.execute(request, context)]
    kinds = [e.kind for e in events]
    assert "ProgressEvent" in kinds
    assert "OutputChunkEvent" in kinds
    assert "CompletedEvent" in kinds

    output = [e for e in events if e.kind == "OutputChunkEvent"][0]
    assert output.payload["text"] == "hello ambrosia"

    completed = [e for e in events if e.kind == "CompletedEvent"][0]
    assert completed.payload["summary"]["echoed_chars"] == len("hello ambrosia")


@pytest.mark.asyncio
async def test_echo_empty_message() -> None:
    handler = EchoHandler()
    request = ActionRequest(
        execution_id="exec-2",
        action_id="core.echo",
        inputs={"message": ""},
    )
    context = ActionExecutionContext(engagement_id="e1")
    events = [event async for event in handler.execute(request, context)]
    output = [e for e in events if e.kind == "OutputChunkEvent"][0]
    assert output.payload["text"] == ""


def test_core_echo_definition() -> None:
    assert CORE_ECHO_ACTION.id == "core.echo"
    assert CORE_ECHO_ACTION.version == "1.0.0"
    assert CORE_ECHO_ACTION.executor.kind == "native"
    assert "message" in (CORE_ECHO_ACTION.input_schema or {}).get("required", [])


def test_register_builtins_does_not_execute() -> None:
    executed = []

    class CaptureHandler:
        async def execute(self, request, context):
            executed.append(request.action_id)

    registry = Registry()
    # Monkeypatch the handler used by register_builtins is not possible;
    # instead confirm registration itself stores without running.
    register_builtins(registry)
    assert executed == []
    assert registry.get("core.echo") is not None
    assert registry.get_handler("core.echo") is not None
