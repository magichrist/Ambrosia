"""Built-in actions, including the ``core.echo`` diagnostic action.

``core.echo`` is provided for end-to-end tests only. Its handler is registered
against the action registry but is never invoked as a side effect of registration
or discovery; it only runs when explicitly executed through the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionHandler,
    ActionRequest,
    ExecutionEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ambrosia.registry.registry import Registry


class EchoHandler(ActionHandler):
    """Echoes the ``message`` input back as stream output events."""

    async def execute(  # noqa: ANN401 - protocol-implementing async-generator handler
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]:
        message = str(request.inputs.get("message", ""))
        yield ExecutionEvent(
            kind="ProgressEvent",
            execution_id=request.execution_id,
            payload={"message": "echoing input", "length": len(message)},
        )
        yield ExecutionEvent(
            kind="OutputChunkEvent",
            execution_id=request.execution_id,
            payload={"stream": "stdout", "text": message},
        )
        yield ExecutionEvent(
            kind="CompletedEvent",
            execution_id=request.execution_id,
            payload={"summary": {"echoed_chars": len(message)}},
        )


CORE_ECHO_ACTION = ActionDefinition(
    id="core.echo",
    version="1.0.0",
    name="Echo / Diagnostic",
    description=(
        "Built-in diagnostic action that echoes its input message back. "
        "Intended for end-to-end tests only; not an assessment capability."
    ),
    category="diagnostic",
    tags=["diagnostic", "builtin", "test"],
    platforms=[],
    phase_refs=[],
    required_artifacts=[],
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo back."}
        },
        "required": ["message"],
        "additionalProperties": False,
    },
    output_artifact_types=[],
    executor=ExecutorReference(kind="native"),
    dependencies=[],
    effects=["local_read"],
    risk="info",
    scope_fields=[],
    approval_required=False,
    timeout_seconds=10,
    max_output_bytes=2_000_000,
    parser_refs=[],
)


def register_builtins(registry: Registry) -> None:
    """Register built-in actions into ``registry`` without executing them."""
    registry.register_builtin(CORE_ECHO_ACTION, handler=EchoHandler())


__all__ = [
    "EchoHandler",
    "CORE_ECHO_ACTION",
    "register_builtins",
]
