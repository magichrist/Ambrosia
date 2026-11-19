"""Executor package public interface.

The process executor (``ProcessExecutor``) is the only built-in executor: it
runs allowlisted executables with argv arrays only and shell=False semantics.
``FakeExecutor`` is provided for tests.
"""

from __future__ import annotations

from ambrosia.executors.base import ExecutorResult, SecretRedactor
from ambrosia.executors.fake import FakeExecutor
from ambrosia.executors.process import ProcessExecutor

__all__ = [
    "ExecutorResult",
    "FakeExecutor",
    "ProcessExecutor",
    "SecretRedactor",
]
