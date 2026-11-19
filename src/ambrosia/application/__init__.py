"""Ambrosia application service layer.

Application services orchestrate the domain layer (models, registry, policy,
storage) for both the Typer CLI and the Textual TUI. CLI commands are thin
presentation wrappers around these services; no business logic lives in the
CLI.

Public interface:

* :class:`ApplicationServices` — the aggregated service container.
* :func:`load_services` — production factory backed by SQLAlchemy storage.
* Individual services: :class:`~ambrosia.application.engagement_service.EngagementService`,
  :class:`~ambrosia.application.scope_service.ScopeService`,
  :class:`~ambrosia.application.target_service.TargetService`,
  :class:`~ambrosia.application.action_service.ActionService`,
  :class:`~ambrosia.application.preset_service.PresetService`,
  :class:`~ambrosia.application.job_service.JobService`,
  :class:`~ambrosia.application.report_service.ReportService`,
  :class:`~ambrosia.application.policy_gateway.PolicyGateway`.

Exit codes are defined in :mod:`ambrosia.application.exit_codes`.
"""

from __future__ import annotations

from ambrosia.application.exit_codes import (
    OK,
    CANCELLED,
    EXECUTION_FAILURE,
    INTERNAL_ERROR,
    MISSING_DEPENDENCY,
    NOT_FOUND,
    POLICY_BLOCKED,
    SCOPE_VIOLATION,
    VALIDATION_ERROR,
    exit_code_for_error,
)
from ambrosia.application.output import OutputFormat, format_json, parse_human_flag
from ambrosia.application.services import ApplicationServices, load_services

__all__ = [
    "ApplicationServices",
    "load_services",
    "OutputFormat",
    "format_json",
    "parse_human_flag",
    "exit_code_for_error",
    "OK",
    "VALIDATION_ERROR",
    "SCOPE_VIOLATION",
    "POLICY_BLOCKED",
    "MISSING_DEPENDENCY",
    "EXECUTION_FAILURE",
    "CANCELLED",
    "NOT_FOUND",
    "INTERNAL_ERROR",
]
