"""CLI command groups wired to application services.

Keep Typer callbacks thin: parse arguments, call an application service,
format the result, and return an exit code. Core business behavior lives in
``ambrosia.application``, which is shared with the Textual TUI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError as PydanticValidationError

from ambrosia.application import (
    MISSING_DEPENDENCY,
    OK,
    POLICY_BLOCKED,
    SCOPE_VIOLATION,
    ApplicationServices,
    exit_code_for_error,
    format_json,
    load_services,
    parse_human_flag,
)
from ambrosia.application.action_service import ActionCheckDTO, ActionDTO, ActionListDTO
from ambrosia.application.engagement_service import EngagementDTO, EngagementListDTO
from ambrosia.application.job_service import JobDTO, JobListDTO, JobShowDTO
from ambrosia.application.preset_service import (
    PresetListDTO,
    PresetPlanDTO,
    PresetValidateDTO,
)
from ambrosia.application.report_service import ReportExportDTO
from ambrosia.application.scope_service import ScopeDTO
from ambrosia.application.target_service import TargetDTO, TargetListDTO
from ambrosia.application.workspace import read_current_engagement, write_current_engagement
from ambrosia.domain.errors import AmbrosiaError, MissingInputError
from ambrosia.storage import Storage, StorageConfig

# Lazy service handle: real services are built on first use so the CLI can be
# imported without a database, and tests can replace it with fakes.
_services: ApplicationServices | None = None


def get_services() -> ApplicationServices:
    """Return the CLI's application service container, building it lazily.

    Production services are backed by a workspace-local SQLite database under
    ``.ambrosia/ambrosia.sqlite`` in the current working directory.
    """
    global _services
    if _services is None:
        storage = Storage(
            config=StorageConfig(
                db_url="sqlite:///.ambrosia/ambrosia.sqlite",
                workspace_root=Path.cwd(),
            )
        )
        from ambrosia.registry.loader import build_registry

        registry = build_registry()
        _services = load_services(
            storage=storage,
            registry=registry,
            presets_dirs=("builtin_presets",),
        )
    return _services


def set_services(services: ApplicationServices) -> None:
    """Replace the service container (used by tests)."""
    global _services
    _services = services


def command[F: Callable[..., Any]](func: F) -> F:
    """Decorator: run a service call, format output, return an exit code.

    The decorated function returns a presentation payload (or a
    ``(payload, exit_code)`` tuple). Ambrosia and Pydantic validation errors
    are mapped to stable exit codes and formatted as JSON when requested.
    """

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> None:
        output = parse_human_flag(kwargs.pop("output", "human"))  # type: ignore[arg-type]
        try:
            outcome = func(*args, **kwargs)
        except (AmbrosiaError, PydanticValidationError) as exc:
            _fail(exc, output)
        if isinstance(outcome, tuple):
            payload, code = outcome
        else:
            payload, code = outcome, OK
        _emit(payload, output)
        raise typer.Exit(code)

    return wrapper  # type: ignore[return-value]


def _emit(payload: Any, output: str) -> None:
    if output == "json":
        typer.echo(format_json(payload), nl=False)
    else:
        typer.echo(_human(payload))


def _fail(exc: Exception, output: str) -> None:
    if isinstance(exc, AmbrosiaError):
        code = exit_code_for_error(exc)
        error_payload: dict[str, object] = {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details or {},
        }
    elif isinstance(exc, PydanticValidationError):
        code = 1  # VALIDATION_ERROR
        error_payload = {
            "code": "validation_error",
            "message": "validation failed",
            "details": {"errors": exc.errors()},
        }
    else:
        code = 99  # INTERNAL_ERROR
        error_payload = {
            "code": "internal_error",
            "message": str(exc),
            "details": {},
        }
    if output == "json":
        typer.echo(format_json({"error": error_payload}), nl=False)
    else:
        typer.echo(f"Error: {error_payload['message']}", err=True)
    raise typer.Exit(code)


def _resolve_engagement(explicit: str | None) -> str:
    if explicit:
        return explicit
    current = read_current_engagement()
    if current is not None:
        return current
    raise MissingInputError(  # noqa: TRY003 - operator-facing message
        "no engagement selected; pass --engagement or run `ambrosia engagement use <id>`"
    )


# ------------------------------------------------------------------ formatting


def _human(value: Any) -> str:
    if isinstance(value, EngagementDTO):
        return f'engagement "{value.name}" (id: {value.id}, status: {value.status})' + (
            f", scope: {value.scope_id}" if value.scope_id else ""
        )
    if isinstance(value, EngagementListDTO):
        if not value.engagements:
            return "no engagements"
        lines = ["engagements:"]
        for engagement in value.engagements:
            lines.append(
                f"  {engagement.id}  {engagement.status:9}  {engagement.name}"
                + (f"  ({engagement.description})" if engagement.description else "")
            )
        return "\n".join(lines)
    if isinstance(value, ScopeDTO):
        lines = [f"scope {value.id} for engagement {value.engagement_id}"]
        lines.append(f"  include_hosts:      {', '.join(value.include_hosts) or '(none)'}")
        lines.append(f"  include_cidrs:      {', '.join(value.include_cidrs) or '(none)'}")
        lines.append(f"  include_domains:    {', '.join(value.include_domains) or '(none)'}")
        lines.append(f"  exclude_hosts:      {', '.join(value.exclude_hosts) or '(none)'}")
        lines.append(f"  exclude_cidrs:      {', '.join(value.exclude_cidrs) or '(none)'}")
        lines.append(
            f"  allowed_ports:      {', '.join(str(p) for p in value.allowed_ports) if value.allowed_ports else '(none)'}"
        )
        lines.append(f"  expires_at:         {value.expires_at or '(none)'}")
        lines.append(f"  max_concurrency:    {value.max_concurrency}")
        lines.append(f"  max_rps:            {value.max_requests_per_second or '(none)'}")
        lines.append(f"  allowed_effects:    {', '.join(value.allowed_effects)}")
        lines.append(f"  require_approval_for: {', '.join(value.require_approval_for)}")
        return "\n".join(lines)
    if isinstance(value, TargetDTO):
        return f"target {value.address} ({value.kind}) id: {value.id}" + (
            f", hostname: {value.hostname}" if value.hostname else ""
        )
    if isinstance(value, TargetListDTO):
        if not value.targets:
            return "no targets"
        lines = ["targets:"]
        for target in value.targets:
            lines.append(f"  {target.id}  {target.kind:6}  {target.address}")
        return "\n".join(lines)
    if isinstance(value, ActionDTO):
        lines = [
            f"action {value.id} (v{value.version})",
            f"  {value.description}",
            f"  category: {value.category}  risk: {value.risk}  executor: {value.executor_kind}",
            f"  effects: {', '.join(value.effects) or '(none)'}",
            f"  approval_required: {value.approval_required}",
            f"  timeout_seconds: {value.timeout_seconds}",
            f"  scope_fields: {', '.join(value.scope_fields) or '(none)'}",
            f"  dependencies: {', '.join(value.dependencies) or '(none)'}",
            f"  required_artifacts: {', '.join(value.required_artifacts) or '(none)'}",
            f"  tags: {', '.join(value.tags) or '(none)'}",
        ]
        return "\n".join(lines)
    if isinstance(value, ActionListDTO):
        if not value.actions:
            return "no actions registered"
        lines = ["actions:"]
        for action in value.actions:
            lines.append(f"  {action.id:40} {action.category:12} {action.name}")
        return "\n".join(lines)
    if isinstance(value, ActionCheckDTO):
        lines = [
            f"action {value.action_id}:",
            f"  status: {value.status}",
            f"  allowed: {'yes' if value.allowed else 'no'}",
        ]
        if value.reasons:
            lines.append("  reasons:")
            for reason in value.reasons:
                lines.append(f"    - {reason}")
        if value.missing_inputs:
            lines.append(f"  missing inputs: {', '.join(value.missing_inputs)}")
        if value.matched_artifact_ids:
            lines.append(f"  matched artifacts: {', '.join(value.matched_artifact_ids)}")
        if value.required_approval:
            lines.append("  approval required: yes")
        return "\n".join(lines)
    if isinstance(value, PresetListDTO):
        if not value.presets:
            return "no presets found"
        lines = ["presets:"]
        for preset in value.presets:
            lines.append(
                f"  {preset.id:40} v{preset.version}  {preset.step_count} steps  {preset.path}"
            )
        return "\n".join(lines)
    if isinstance(value, PresetValidateDTO):
        lines = [
            f"preset {value.path}: {'valid' if value.valid else 'invalid'}",
            f"  steps: {value.step_count}",
        ]
        if value.errors:
            lines.append("  errors:")
            for error in value.errors:
                lines.append(f"    - {error}")
        if value.warnings:
            lines.append("  warnings:")
            for warning in value.warnings:
                lines.append(f"    - {warning}")
        return "\n".join(lines)
    if isinstance(value, PresetPlanDTO):
        lines = [f"plan for preset {value.preset_id} (v{value.version}, dry-run)"]
        if value.input_requests:
            lines.append("  preset inputs required: " + ", ".join(value.input_requests))
        lines.append("  steps:")
        for step in value.steps:
            lines.append(f"    {step.id:20} {step.type:10} {step.action or '-':35} {step.status}")
            for reason in step.reasons:
                lines.append(f"          - {reason}")
            if step.missing_inputs:
                lines.append(f"          missing inputs: {', '.join(step.missing_inputs)}")
        return "\n".join(lines)
    if isinstance(value, JobDTO):
        return (
            f"job {value.id} ({value.status})"
            + (f" action: {value.action_id}" if value.action_id else "")
            + (f" preset: {value.preset_id}" if value.preset_id else "")
        )
    if isinstance(value, JobListDTO):
        if not value.jobs:
            return "no executions"
        lines = ["executions:"]
        for job in value.jobs:
            lines.append(f"  {job.id}  {job.status:12}  {job.action_id or job.preset_id or '-'}")
        return "\n".join(lines)
    if isinstance(value, JobShowDTO):
        lines = [_human(value.job).replace("job ", "execution ", 1)]
        lines.append("  events:")
        if not value.events:
            lines.append("    (none)")
        for event in value.events:
            lines.append(f"    [{event.sequence}] {event.kind}")
        return "\n".join(lines)
    if isinstance(value, ReportExportDTO):
        return (
            f"report exported to {value.path} "
            f"({value.targets} targets, {value.artifacts} artifacts, {value.executions} executions)"
        )
    return str(value)


# ------------------------------------------------------------------ engagement

engagement_app = typer.Typer(
    name="engagement",
    help="Create, list, and open engagements.",
)


@engagement_app.command("create")
@command
def engagement_create(
    name: str = typer.Argument(..., help="Engagement name."),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Engagement description."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> EngagementDTO:
    """Create a new engagement with an empty, conservative scope."""
    return get_services().engagement.create(name=name, description=description)


@engagement_app.command("list")
@command
def engagement_list(
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> EngagementListDTO:
    """List engagements."""
    return get_services().engagement.list()


@engagement_app.command("use")
@command
def engagement_use(
    engagement_id: str = typer.Argument(..., help="Engagement id to use."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> EngagementDTO:
    """Open an engagement and record it as the current engagement."""
    services = get_services()
    dto = services.engagement.open(engagement_id)
    write_current_engagement(engagement_id)
    return dto


# ------------------------------------------------------------------ scope

scope_app = typer.Typer(name="scope", help="Show and update engagement scope.")


@scope_app.command("show")
@command
def scope_show(
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> ScopeDTO:
    """Show the current engagement scope."""
    return get_services().scope.show(_resolve_engagement(engagement))


@scope_app.command("update")
@command
def scope_update(
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    include_host: list[str] = typer.Option(
        None, "--include-host", help="Authorized host (repeatable)."
    ),
    include_cidr: list[str] = typer.Option(
        None, "--include-cidr", help="Authorized CIDR (repeatable)."
    ),
    include_domain: list[str] = typer.Option(
        None, "--include-domain", help="Authorized domain (repeatable)."
    ),
    exclude_host: list[str] = typer.Option(
        None, "--exclude-host", help="Excluded host (repeatable)."
    ),
    exclude_cidr: list[str] = typer.Option(
        None, "--exclude-cidr", help="Excluded CIDR (repeatable)."
    ),
    allowed_port: list[int] = typer.Option(
        None, "--allowed-port", help="Allowed port (repeatable)."
    ),
    expires_at: str | None = typer.Option(
        None, "--expires-at", help="Scope expiration (ISO-8601)."
    ),
    max_concurrency: int | None = typer.Option(
        None, "--max-concurrency", help="Maximum concurrent executions."
    ),
    allowed_effect: list[str] = typer.Option(
        None, "--allowed-effect", help="Allowed effect class (repeatable)."
    ),
    require_approval_for: list[str] = typer.Option(
        None, "--require-approval-for", help="Effect requiring approval (repeatable)."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> ScopeDTO:
    """Update the engagement scope (creates it if missing)."""
    return get_services().scope.update(
        _resolve_engagement(engagement),
        include_hosts=include_host,
        include_cidrs=include_cidr,
        include_domains=include_domain,
        exclude_hosts=exclude_host,
        exclude_cidrs=exclude_cidr,
        allowed_ports=allowed_port,
        expires_at=expires_at,
        max_concurrency=max_concurrency,
        allowed_effects=allowed_effect,
        require_approval_for=require_approval_for,
    )


# ------------------------------------------------------------------ target

target_app = typer.Typer(name="target", help="Add and list targets.")


@target_app.command("add")
@command
def target_add(
    address: str = typer.Argument(..., help="Target host, IP address, or domain."),
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    kind: str = typer.Option(
        "auto",
        "--kind",
        help="Target kind: auto, host, ip, or domain.",
    ),
    hostname: str | None = typer.Option(None, "--hostname", help="Hostname alias."),
    notes: str | None = typer.Option(None, "--notes", help="Target notes."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> TargetDTO:
    """Add a target to the engagement scope."""
    return get_services().target.add(
        _resolve_engagement(engagement), address, kind=kind, hostname=hostname, notes=notes
    )


@target_app.command("list")
@command
def target_list(
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> TargetListDTO:
    """List targets for the engagement."""
    return get_services().target.list(_resolve_engagement(engagement))


# ------------------------------------------------------------------ actions

action_app = typer.Typer(name="actions", help="List, inspect, and check actions.")


@action_app.command("list")
@command
def actions_list(
    category: str | None = typer.Option(None, "--category", help="Filter by category."),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag."),
    platform: str | None = typer.Option(None, "--platform", help="Filter by platform."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> ActionListDTO:
    """List registered actions."""
    return get_services().action.list(category=category, tag=tag, platform=platform)


@action_app.command("info")
@command
def actions_info(
    action_id: str = typer.Argument(..., help="Action id."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> ActionDTO:
    """Show action details."""
    return get_services().action.info(action_id)


@action_app.command("check")
@command
def actions_check(
    action_id: str = typer.Argument(..., help="Action id."),
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    target: str | None = typer.Option(None, "--target", help="Target address for the scope check."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> tuple[ActionCheckDTO, int]:
    """Check whether an action is available and why.

    The exit code reflects availability: 0 when available, non-zero when the
    action is blocked by scope, policy, or a missing dependency.
    """
    availability = get_services().action.check(
        action_id,
        engagement_id=_resolve_engagement(engagement),
        target_address=target,
    )
    code = _check_exit_code(availability)
    return availability, code


def _check_exit_code(availability: ActionCheckDTO) -> int:
    if availability.allowed:
        return OK
    if availability.status == "missing_dependency":
        return MISSING_DEPENDENCY
    if availability.status == "blocked":
        if any(reason.startswith("blocked by scope") for reason in availability.reasons):
            return SCOPE_VIOLATION
        return POLICY_BLOCKED
    return POLICY_BLOCKED  # needs_approval / needs_input treated as blocked for automation


# ------------------------------------------------------------------ preset

preset_app = typer.Typer(name="preset", help="Validate, plan, and run presets.")


@preset_app.command("list")
@command
def preset_list(
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> PresetListDTO:
    """List available presets."""
    return get_services().preset.list()


@preset_app.command("validate")
@command
def preset_validate(
    path: str = typer.Argument(..., help="Path to a preset YAML file."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> PresetValidateDTO:
    """Validate a preset YAML file without executing it."""
    return get_services().preset.validate(path)


@preset_app.command("plan")
@command
def preset_plan(
    preset_id: str = typer.Argument(..., help="Preset id."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> PresetPlanDTO:
    """Produce a dry-run execution plan for a preset (no action runs)."""
    return get_services().preset.plan(preset_id)


@preset_app.command("run")
@command
def preset_run(
    preset_id: str = typer.Argument(..., help="Preset id."),
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (required)."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> Any:
    """Run a preset. Policy is enforced for every action step before execution."""
    services = get_services()
    engagement_id = _resolve_engagement(engagement)
    return asyncio.run(services.preset.run(preset_id, engagement_id=engagement_id, inputs=None))


# ------------------------------------------------------------------ jobs

job_app = typer.Typer(name="jobs", help="List and show executions.")


@job_app.command("list")
@command
def jobs_list(
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> JobListDTO:
    """List executions for the engagement."""
    return get_services().job.list(_resolve_engagement(engagement))


@job_app.command("show")
@command
def jobs_show(
    job_id: str = typer.Argument(..., help="Execution id."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> JobShowDTO:
    """Show execution details and events."""
    return get_services().job.show(job_id)


@job_app.command("cancel")
@command
def jobs_cancel(
    job_id: str = typer.Argument(..., help="Execution id."),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> JobDTO:
    """Cancel an execution."""
    return get_services().job.cancel(job_id)


# ------------------------------------------------------------------ report

report_app = typer.Typer(name="report", help="Export evidence/reports.")


@report_app.command("export")
@command
def report_export(
    engagement: str | None = typer.Option(
        None, "--engagement", "-e", help="Engagement id (defaults to current)."
    ),
    format: str = typer.Option("json", "--format", help="Report format (json)."),
    output_file: str | None = typer.Option(
        None, "--output-file", help="Report file path (default: ./ambrosia-report-<id>.json)."
    ),
    output: str = typer.Option("human", "--output", help="Output format: human or json."),
) -> ReportExportDTO:
    """Export an engagement evidence bundle."""
    return get_services().report.export(
        _resolve_engagement(engagement), format=format, output_path=output_file
    )


# Register all sub-apps with the root app in main.py via the commands package.
__all__ = [
    "engagement_app",
    "scope_app",
    "target_app",
    "action_app",
    "preset_app",
    "job_app",
    "report_app",
    "get_services",
    "set_services",
]
