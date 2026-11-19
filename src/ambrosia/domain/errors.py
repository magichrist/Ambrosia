"""Stable error hierarchy for Ambrosia.

Public errors carry a stable ``code``, a safe human-readable message, and
structured non-secret details. Secret values must never appear in exception
messages.
"""

from __future__ import annotations

from typing import Any


class AmbrosiaError(Exception):
    """Base error for all Ambrosia domain/application failures."""

    code: str = "ambrosia_error"
    message: str = "An Ambrosia error occurred."
    details: dict[str, Any] | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        if code is not None:
            self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class ValidationError(AmbrosiaError):
    """Input or manifest validation failed."""

    code = "validation_error"
    message = "Validation failed."


class NotFoundError(AmbrosiaError):
    """A requested resource was not found."""

    code = "not_found"
    message = "Resource not found."


class ConflictError(AmbrosiaError):
    """The current state conflicts with the requested operation."""

    code = "conflict"
    message = "Conflict with current state."


class ScopeViolationError(AmbrosiaError):
    """A target or operation falls outside the engagement scope."""

    code = "scope_violation"
    message = "Operation is outside the authorized engagement scope."


class PolicyBlockedError(AmbrosiaError):
    """Policy or approval requirements block execution."""

    code = "policy_blocked"
    message = "Execution is blocked by policy."


class MissingInputError(AmbrosiaError):
    """A required user input is missing."""

    code = "missing_input"
    message = "A required input is missing."


class MissingDependencyError(AmbrosiaError):
    """A required local tool, pack, or runtime is unavailable."""

    code = "missing_dependency"
    message = "A required dependency is missing."


class ExecutionError(AmbrosiaError):
    """An action or preset execution failed."""

    code = "execution_error"
    message = "Execution failed."


class ExecutionTimeoutError(ExecutionError):
    """Execution exceeded its timeout."""

    code = "execution_timeout"
    message = "Execution timed out."


class ExecutionCancelledError(ExecutionError):
    """Execution was cancelled by the operator."""

    code = "execution_cancelled"
    message = "Execution was cancelled."


class ParseError(AmbrosiaError):
    """Parsing of tool output or a preset document failed."""

    code = "parse_error"
    message = "Parse failed."
