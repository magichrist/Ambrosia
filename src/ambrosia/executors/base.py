"""Executor base: result types and secret redaction.

Executors implement the :class:`~ambrosia.domain.protocols.ActionHandler`
protocol. The process executor (``process.py``) is the only built-in
executor; it runs allowlisted executables with argv arrays only and
``shell=False`` semantics.
"""

from __future__ import annotations


class ExecutorResult:
    """Outcome of an executor run.

    Captures exit code, captured (redacted) output, duration, and terminal
    state (timed out / cancelled).
    """

    def __init__(
        self,
        *,
        execution_id: str,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        duration_seconds: float = 0.0,
        timed_out: bool = False,
        cancelled: bool = False,
        error: str | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration_seconds = duration_seconds
        self.timed_out = timed_out
        self.cancelled = cancelled
        self.error = error

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "error": self.error,
        }


class SecretRedactor:
    """Redacts known secret values from text.

    Secrets are added explicitly (e.g. resolved secret handles' display
    values). Redaction replaces each occurrence with ``[REDACTED]``. Applied to
    stdout, stderr, logs, and command previews.
    """

    def __init__(self, secrets: set[str] | None = None) -> None:
        self._secrets: set[str] = set(secrets or set())

    def add_secret(self, value: str) -> None:
        if value:
            self._secrets.add(value)

    def redact(self, text: str) -> str:
        """Return ``text`` with known secret values replaced by ``[REDACTED]``."""
        if not text or not self._secrets:
            return text
        result = text
        # Longer secrets first so a longer secret isn't partially matched by a
        # shorter one that is a substring.
        for secret in sorted(self._secrets, key=len, reverse=True):
            result = result.replace(secret, "[REDACTED]")
        return result

    def redact_dict(
        self,
        data: dict[str, object],
        secret_keys: set[str] | None = None,
    ) -> dict[str, object]:
        """Return a copy of ``data`` with secret-valued keys replaced."""
        keys = secret_keys or {
            "password",
            "passwd",
            "secret",
            "token",
            "key",
            "credential",
            "hash",
        }
        result: dict[str, object] = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in keys:
                result[key] = "[REDACTED]"
            else:
                result[key] = value
        return result


__all__ = ["ExecutorResult", "SecretRedactor"]
