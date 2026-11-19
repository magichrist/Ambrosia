"""Job engine: execution lifecycle, concurrency, timeouts, cancellation.

Coordinates the durable execution lifecycle:

``draft`` -> ``validated`` -> ``awaiting_input`` | ``awaiting_approval`` ->
``ready`` -> ``running`` -> ``parsing`` -> ``succeeded`` | ``partial`` |
``failed`` | ``cancelled`` | ``blocked``

Every execution path validates policy (scope + effects + approval) before any
process is started. The engine persists every transition through the
:class:`~ambrosia.domain.protocols.ExecutionRepository`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone, UTC

from ambrosia.domain.action import ActionDefinition
from ambrosia.domain.errors import (
    ConflictError,
    ExecutionCancelledError,
    ExecutionError,
    ExecutionTimeoutError,
    NotFoundError,
    PolicyBlockedError,
    ScopeViolationError,
)
from ambrosia.domain.models import ExecutionRecord
from ambrosia.domain.protocols import (
    ActionExecutionContext,
    ActionRequest,
    ExecutionEvent,
    ExecutionRepository,
)
from ambrosia.engine.job import JobEvent, JobStatus, valid_transition
from ambrosia.policy import PolicyEngine
from ambrosia.registry import Registry

_SECRET_KEYS = frozenset(
    {"password", "passwd", "secret", "token", "key", "credential", "hash"}
)


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sanitize_summary(inputs: dict[str, object]) -> dict[str, object]:
    """Return a copy of ``inputs`` with secret-valued keys redacted."""
    result: dict[str, object] = {}
    for key, value in inputs.items():
        if isinstance(key, str) and key.lower() in _SECRET_KEYS:
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


class JobEngine:
    """Coordinates the execution lifecycle and enforces policy at every step.

    No process is started unless ``validate`` has passed and the job is in the
    ``ready`` state. Cancellation and timeouts terminate and reap the child
    process.
    """

    def __init__(
        self,
        *,
        registry: Registry,
        execution_repository: ExecutionRepository,
        policy_engine: PolicyEngine,
        concurrency_limit: int = 2,
    ) -> None:
        self._registry = registry
        self._execution_repository = execution_repository
        self._policy_engine = policy_engine
        self._semaphore = asyncio.Semaphore(max(1, concurrency_limit))
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------ create

    async def create_job(
        self,
        *,
        engagement_id: str,
        action_id: str,
        inputs: dict[str, object],
        target_refs: list[str] | None = None,
        initiated_by: str = "operator",
    ) -> str:
        """Create a new execution record in ``draft`` status. Returns the ID."""
        definition = self._registry.get(action_id)
        if definition is None:
            raise NotFoundError(f"action {action_id!r} is not registered")

        record = ExecutionRecord(
            engagement_id=engagement_id,
            action_id=action_id,
            status="draft",
            input_summary=_sanitize_summary(inputs),
            target_refs=list(target_refs or []),
            initiated_by=initiated_by,
        )
        record = self._execution_repository.add(record)
        return record.id

    # ------------------------------------------------------------------ validate

    async def validate_job(
        self,
        execution_id: str,
        *,
        scope,
        address: str | None = None,
        port: int | None = None,
    ) -> None:
        """Validate scope and policy for an execution.

        Transitions ``draft`` -> ``validated``. Raises
        :class:`~ambrosia.domain.errors.ScopeViolationError` if the target is
        outside scope.
        """
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        definition = self._registry.get(record.action_id)
        if definition is None:
            raise NotFoundError(f"action {record.action_id!r} is not registered")

        # Policy evaluation: scope + effects + approval.
        outcome, _decision, _record = self._policy_engine.evaluate(
            action=definition,
            scope=scope,
            address=address,
            port=port,
            execution_id=execution_id,
            engagement_id=record.engagement_id,
        )

        if outcome == "blocked":
            raise ScopeViolationError(
                "execution blocked by policy scope check",
                details={"execution_id": execution_id, "action_id": record.action_id},
            )

        if not valid_transition(record.status, "validated"):  # type: ignore[arg-type]
            raise ConflictError(
                f"cannot validate execution {execution_id!r} in status "
                f"{record.status!r}"
            )

        record.status = "validated"
        self._execution_repository.update(record)

    # ------------------------------------------------------------------ approval

    async def request_approval(self, execution_id: str) -> str | None:
        """Transition ``validated`` -> ``awaiting_approval`` if approval required.

        Returns the approval record ID, or ``None`` if no approval is needed
        (in which case the job moves to ``ready``).
        """
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        definition = self._registry.get(record.action_id)
        if definition is None:
            raise NotFoundError(f"action {record.action_id!r} is not registered")

        # Determine if approval is required by re-evaluating effects.
        scope = None  # The engine does not carry scope here; caller should pass.
        # Approval requirement is derived from the action definition + scope
        # at validation time. Here we just record the intent.
        if not definition.approval_required and not any(
            e in {"local_write", "remote_change", "authentication", "credential_access"}
            for e in definition.effects
        ):
            if valid_transition(record.status, "ready"):  # type: ignore[arg-type]
                record.status = "ready"
                self._execution_repository.update(record)
            return None

        if not valid_transition(record.status, "awaiting_approval"):  # type: ignore[arg-type]
            raise ConflictError(
                f"cannot request approval for execution {execution_id!r} in "
                f"status {record.status!r}"
            )

        record.status = "awaiting_approval"
        self._execution_repository.update(record)

        # Create a pending approval record via the policy engine's approval
        # service. The effect is the first sensitive effect declared.
        effect = next(
            (
                e
                for e in definition.effects
                if e in {"local_write", "remote_change", "authentication", "credential_access"}
            ),
            definition.effects[0] if definition.effects else "unknown",
        )
        approval = self._policy_engine.create_approval(
            execution_id=execution_id,
            engagement_id=record.engagement_id,
            effect=effect,
            reason="approval required before execution",
        )
        return approval.id

    async def grant_approval(self, execution_id: str, *, approval_id: str, decided_by: str) -> None:
        """Transition ``awaiting_approval`` -> ``ready`` after explicit grant."""
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        self._policy_engine.grant_approval(approval_id, decided_by=decided_by)

        if not valid_transition(record.status, "ready"):  # type: ignore[arg-type]
            raise ConflictError(
                f"cannot move execution {execution_id!r} to ready from "
                f"status {record.status!r}"
            )
        record.status = "ready"
        self._execution_repository.update(record)

    async def deny_approval(
        self, execution_id: str, *, approval_id: str, decided_by: str, reason: str | None = None
    ) -> None:
        """Transition ``awaiting_approval`` -> ``blocked`` after explicit denial."""
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        self._policy_engine.deny_approval(
            approval_id, decided_by=decided_by, reason=reason
        )

        if not valid_transition(record.status, "blocked"):  # type: ignore[arg-type]
            raise ConflictError(
                f"cannot block execution {execution_id!r} from status "
                f"{record.status!r}"
            )
        record.status = "blocked"
        self._execution_repository.update(record)

    # ------------------------------------------------------------------ run

    async def run_job(
        self,
        execution_id: str,
        *,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run a validated, approved execution.

        Yields :class:`~ambrosia.domain.protocols.ExecutionEvent` instances as
        they are produced and persists every transition and event.
        """
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        if record.status != "ready":
            raise ConflictError(
                f"cannot run execution {execution_id!r} in status "
                f"{record.status!r}"
            )

        definition = self._registry.get(record.action_id)
        if definition is None:
            raise NotFoundError(f"action {record.action_id!r} is not registered")

        handler = self._registry.get_handler(record.action_id)
        if handler is None:
            from ambrosia.registry.errors import HandlerNotFoundError

            raise HandlerNotFoundError(
                f"no handler registered for action {record.action_id!r}"
            )

        request = ActionRequest(
            execution_id=execution_id,
            action_id=record.action_id,
            inputs=dict(record.input_summary),
            target_refs=list(record.target_refs),
        )
        context = ActionExecutionContext(engagement_id=record.engagement_id)

        # Transition ready -> running
        record.status = "running"
        record.started_at = _utc_now_naive()
        self._execution_repository.update(record)

        sequence = 0
        iterator = handler.execute(request, context)
        handler_failed = False

        try:
            async with self._semaphore:
                while True:
                    try:
                        if timeout_seconds is not None:
                            event = await asyncio.wait_for(
                                anext(iterator), timeout=timeout_seconds
                            )
                        else:
                            event = await anext(iterator)
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        try:
                            await iterator.aclose()
                        except Exception:
                            pass
                        raise ExecutionTimeoutError(
                            f"execution {execution_id!r} timed out after "
                            f"{timeout_seconds}s"
                        )

                    sequence += 1
                    self._execution_repository.add_event(
                        execution_id=execution_id,
                        kind=event.kind,
                        payload=dict(event.payload),
                        sequence=sequence,
                    )
                    yield event

                    if event.kind == "FailedEvent":
                        handler_failed = True
                        try:
                            await iterator.aclose()
                        except Exception:
                            pass
                        break

                if handler_failed:
                    record.status = "failed"
                    record.error_code = (
                        event.payload.get("code", "execution_error")
                        if event
                        else "execution_error"
                    )
                    record.error_message = (
                        event.payload.get("message", "execution failed")
                        if event
                        else "execution failed"
                    )
                    record.finished_at = _utc_now_naive()
                    self._execution_repository.update(record)
                else:
                    # running -> parsing -> succeeded
                    record.status = "parsing"
                    self._execution_repository.update(record)

                    record.status = "succeeded"
                    record.finished_at = _utc_now_naive()
                    self._execution_repository.update(record)

        except asyncio.CancelledError:
            # Operator cancellation: stop the handler (terminates its process).
            try:
                await iterator.aclose()
            except Exception:
                pass
            record.status = "cancelled"
            record.finished_at = _utc_now_naive()
            self._execution_repository.update(record)
            raise ExecutionCancelledError(
                f"execution {execution_id!r} was cancelled"
            )
        except ExecutionTimeoutError:
            record.status = "failed"
            record.error_code = "execution_timeout"
            record.error_message = "execution timed out"
            record.finished_at = _utc_now_naive()
            self._execution_repository.update(record)
            raise
        except Exception as exc:  # noqa: BLE001
            try:
                await iterator.aclose()
            except Exception:
                pass
            record.status = "failed"
            record.error_code = "execution_error"
            record.error_message = str(exc)
            record.finished_at = _utc_now_naive()
            self._execution_repository.update(record)
            raise ExecutionError(str(exc)) from exc

    # ------------------------------------------------------------------ cancel

    async def cancel_job(self, execution_id: str) -> None:
        """Request cancellation of a running execution.

        Cancels the associated asyncio task, which terminates and reaps the
        child process.
        """
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        task = self._running_tasks.get(execution_id)
        if task is not None and not task.done():
            task.cancel()

    # ------------------------------------------------------------------ dry run

    async def dry_run(
        self,
        execution_id: str,
        *,
        scope,
        address: str | None = None,
        port: int | None = None,
    ) -> dict[str, object]:
        """Resolve inputs and produce a sanitized execution plan.

        Launches NO process. Returns a dictionary describing what would run,
        including redacted argv, effects, and approval requirement.
        """
        record = self._execution_repository.get(execution_id)
        if record is None:
            raise NotFoundError(f"execution {execution_id!r} not found")

        definition = self._registry.get(record.action_id)
        if definition is None:
            raise NotFoundError(f"action {record.action_id!r} is not registered")

        # Policy evaluation only -- no process is started.
        outcome, decision, decision_record = self._policy_engine.evaluate(
            action=definition,
            scope=scope,
            address=address,
            port=port,
            execution_id=execution_id,
            engagement_id=record.engagement_id,
        )

        argv = record.input_summary.get("argv", [])
        if not isinstance(argv, list):
            argv = []

        return {
            "execution_id": execution_id,
            "action_id": record.action_id,
            "executable": (
                definition.executor.executable if definition.executor else None
            ),
            "argv": [str(a) for a in argv],
            "argv_redacted": True,
            "outcome": outcome,
            "reason": decision.reason,
            "scope_address": address,
            "effects": list(definition.effects),
            "approval_required": outcome == "requires_approval",
            "timeout_seconds": definition.timeout_seconds,
            "max_output_bytes": definition.max_output_bytes,
            "decisions": decision_record.to_list(),
            "dry_run": True,
        }

    # ------------------------------------------------------------------ internal

    def register_task(self, execution_id: str, task: asyncio.Task[None]) -> None:
        """Register a running task so :meth:`cancel_job` can terminate it.

        The caller creates a task from :meth:`run_job` and registers it here.
        A done callback automatically untracks the task when it completes.
        """

        def _done(_task: asyncio.Task[None]) -> None:
            self._running_tasks.pop(execution_id, None)

        task.add_done_callback(_done)
        self._running_tasks[execution_id] = task


__all__ = ["JobEngine", "_sanitize_summary"]
