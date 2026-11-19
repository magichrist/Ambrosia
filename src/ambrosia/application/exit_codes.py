"""Process exit codes for the Ambrosia CLI.

Every command returns one of these codes. They are stable across releases so
automation can branch on them (for example ``if ambrosia preset run ...; then``).

The codes map one-to-one to the domain error codes in
``ambrosia.domain.errors``: see :func:`exit_code_for_error`.
"""

from __future__ import annotations

# Successful completion.
OK = 0

# --- Client errors (1xx) ---

# Input or manifest validation failed (also covers missing required inputs).
VALIDATION_ERROR = 1
# A target or operation falls outside the authorized engagement scope.
SCOPE_VIOLATION = 2
# Policy or approval requirements block execution.
POLICY_BLOCKED = 3
# A required local tool, pack, runtime, or integration is missing.
MISSING_DEPENDENCY = 4

# --- Execution errors (5xx) ---

# An action or preset execution failed (includes timeouts).
EXECUTION_FAILURE = 5
# Execution was cancelled by the operator.
CANCELLED = 6

# --- Resource errors ---

# A requested engagement, scope, target, preset, or job was not found.
NOT_FOUND = 7

# Unexpected internal error.
INTERNAL_ERROR = 99


_ERROR_CODE_TO_EXIT_CODE: dict[str, int] = {
    "validation_error": VALIDATION_ERROR,
    "missing_input": VALIDATION_ERROR,
    "scope_violation": SCOPE_VIOLATION,
    "policy_blocked": POLICY_BLOCKED,
    "missing_dependency": MISSING_DEPENDENCY,
    "execution_error": EXECUTION_FAILURE,
    "execution_timeout": EXECUTION_FAILURE,
    "execution_cancelled": CANCELLED,
    "not_found": NOT_FOUND,
    "conflict": VALIDATION_ERROR,
    "parse_error": VALIDATION_ERROR,
}


def exit_code_for_error(error: Exception) -> int:
    """Return the exit code for an error raised by an application service.

    :class:`~ambrosia.domain.errors.AmbrosiaError` instances carry a stable
    ``code`` that maps to an exit code. Anything else is treated as an
    internal error.
    """
    from ambrosia.domain.errors import AmbrosiaError

    if isinstance(error, AmbrosiaError):
        return _ERROR_CODE_TO_EXIT_CODE.get(error.code, INTERNAL_ERROR)
    return INTERNAL_ERROR


__all__ = [
    "OK",
    "VALIDATION_ERROR",
    "SCOPE_VIOLATION",
    "POLICY_BLOCKED",
    "MISSING_DEPENDENCY",
    "EXECUTION_FAILURE",
    "CANCELLED",
    "NOT_FOUND",
    "INTERNAL_ERROR",
    "exit_code_for_error",
]
