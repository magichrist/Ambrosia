"""Handlers for the opt-in authorized operations pack.

Each handler:

1. requires an explicit authorization reference (handler-level gate),
2. builds a bounded argv array for an allowlisted installed binary,
3. runs it through the injected shell-free executor, and
4. emits events without persisting raw credential material by default.

Raw tool output is emitted only when the operator sets ``show_output: true``.
Execution events are persisted by the engine, so that option explicitly opts
in to storing potentially sensitive output in execution history.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ambrosia.domain.errors import PolicyBlockedError
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionHandler,
    ActionRequest,
    ExecutionEvent,
)
from ambrosia.packs.authorized_operations.argv import (
    build_domain_enumeration_argv,
    build_netexec_argv,
    build_netexec_exec_argv,
    build_ntlm_relay_argv,
    build_psexec_argv,
    build_samdump2_argv,
    build_secretsdump_argv,
)
from ambrosia.policy.authorization import require_request_authorization

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ambrosia.domain.action import ActionDefinition

ArgvBuilder = Callable[[dict[str, object]], list[str]]

_BUILDERS: dict[str, ArgvBuilder] = {
    "windows.credentials.secretsdump": build_secretsdump_argv,
    "windows.credentials.samdump2": build_samdump2_argv,
    "windows.smb.netexec": build_netexec_argv,
    "windows.lateral.netexec_exec": build_netexec_exec_argv,
    "windows.lateral.psexec": build_psexec_argv,
    "windows.ad.domain_enumeration": build_domain_enumeration_argv,
    "windows.smb.ntlm_relay": build_ntlm_relay_argv,
}


class AuthorizedToolHandler(ActionHandler):
    """Runs one allowlisted high-impact tool behind an authorization gate."""

    def __init__(
        self,
        executor: ActionHandler,
        definition: ActionDefinition,
        *,
        builder: ArgvBuilder | None = None,
    ) -> None:
        self._executor = executor
        self._definition = definition
        self._builder = builder or _BUILDERS[definition.id]

    async def execute(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]:
        execution_id = request.execution_id

        # Gate before any argv is built or any process is started.
        try:
            authorization = require_request_authorization(request, self._definition)
            argv = self._builder(dict(request.inputs))
        except (PolicyBlockedError, ValueError) as exc:
            yield ExecutionEvent(
                kind="FailedEvent",
                execution_id=execution_id,
                payload={
                    "code": "authorization_or_input_error",
                    "message": str(exc),
                    "retryable": False,
                },
            )
            return

        yield ExecutionEvent(
            kind="ProgressEvent",
            execution_id=execution_id,
            payload={
                "message": f"authorized operation {self._definition.id} starting",
                "action": self._definition.id,
                "authorization_reference": authorization.reference,
                "argv_length": len(argv),
            },
        )

        exec_request = ActionRequest(
            execution_id=execution_id,
            action_id=self._definition.id,
            inputs={"argv": argv},
        )
        output_parts: list[str] = []
        exit_code: object = None
        try:
            async for event in self._executor.execute(exec_request, context):
                if event.kind == "OutputChunkEvent":
                    output_parts.append(str(event.payload.get("text", "")))
                elif event.kind == "FailedEvent":
                    yield event
                    return
                elif event.kind == "CompletedEvent":
                    summary = event.payload.get("summary")
                    if isinstance(summary, dict):
                        exit_code = summary.get("exit_code")
        except Exception as exc:  # noqa: BLE001 - translate to typed failure
            yield ExecutionEvent(
                kind="FailedEvent",
                execution_id=execution_id,
                payload={
                    "code": "execution_error",
                    "message": f"{self._definition.id} failed: {exc}",
                    "retryable": False,
                },
            )
            return

        output = "".join(output_parts)
        # Raw output is persisted by the engine as an event. Only emit it when
        # the operator explicitly opts in; otherwise emit metadata only.
        if request.inputs.get("show_output") is True and output:
            yield ExecutionEvent(
                kind="OutputChunkEvent",
                execution_id=execution_id,
                payload={"stream": "stdout", "text": output},
            )

        yield ExecutionEvent(
            kind="CompletedEvent",
            execution_id=execution_id,
            payload={
                "summary": {
                    "action": self._definition.id,
                    "exit_code": exit_code,
                    "output_bytes": len(output.encode("utf-8")),
                    "output_retained": bool(request.inputs.get("show_output") is True and output),
                    "authorization_reference": authorization.reference,
                }
            },
        )


__all__ = ["AuthorizedToolHandler"]
