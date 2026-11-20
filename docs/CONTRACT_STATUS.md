# Contract status

This document identifies the frozen public interfaces and the deliberate
deviations from `00_MASTER_PLAN.md` / `01_SHARED_CONTRACTS.md`. It is the
reference for contributors adding to the codebase.

## Frozen interfaces

| Area | Public surface | Location |
|---|---|---|
| Domain models | `Engagement`, `Scope`, `Target`, `Artifact`, `ExecutionRecord`, `Observation`, `Finding` | `src/ambrosia/domain/models.py` |
| Action contract | `ActionDefinition`, `ActionAvailability`, `ArtifactRequirement`, `ExecutorReference`, `ToolDependency` | `src/ambrosia/domain/action.py` |
| Action handler | `ActionHandler`, `ActionRequest`, `ActionExecutionContext`, event variants | `src/ambrosia/domain/protocols.py`, `src/ambrosia/domain/protocols.py` |
| Preset contract | `PresetDefinition`, `PresetStep`, `PresetInput`, `OutputBinding`, `PresetMetadata` | `src/ambrosia/domain/preset.py` |
| Phase contract | `PhaseDefinition`, `Predicate` | `src/ambrosia/domain/phase.py` |
| Artifact lifecycle | `create_artifact` and built-in type schemas | `src/ambrosia/artifacts/` |
| Context | `ContextSnapshot`, context service and events | `src/ambrosia/context/`, `src/ambrosia/domain/context.py` |
| Registry | `Registry`, `PackManifest`, `LoadResult`, availability matcher | `src/ambrosia/registry/` |
| Presets engine | `PresetLoader`, `PresetPlan`, `StepNode`, resolver, predicates | `src/ambrosia/presets/` |
| Policy | `PolicyEngine`, scope matcher, effect classifier, approvals | `src/ambrosia/policy/` |
| Execution | `JobEngine`, `ProcessExecutor`, `FakeExecutor`, Nmap adapter | `src/ambrosia/engine/`, `src/ambrosia/executors/` |
| Storage protocols | repository Protocols; ORM models private to storage | `src/ambrosia/domain/protocols.py`, `src/ambrosia/storage/` |
| Application services | `ApplicationServices`, DTOs in each `*_service.py` | `src/ambrosia/application/` |
| Errors | `AmbrosiaError` hierarchy with stable codes | `src/ambrosia/domain/errors.py` |

Domain models do not import Textual, Typer, SQLAlchemy, or concrete tools.
Repositories return domain objects, never ORM instances.

## Deliberate deviations from the plan

1. **Packaging: setuptools, not Poetry.** `pyproject.toml` uses the setuptools
   build backend and there is no `poetry.lock`. Dependencies are pinned with
   compatible ranges and the wheel/sdist build is exercised in CI. `pip install
   -e ".[dev]"` is the supported developer install.
2. **`ActionHandler.execute` is a synchronous method returning
   `AsyncIterator[ExecutionEvent]`.** Implementations are async generators;
   declaring the method `async def` would describe an `AsyncIterator` *awaited
   as a value* and produced hundreds of false mypy errors. The current
   declaration matches the actual call pattern (`async for event in handler.execute(...)`).
3. **Engine-only preset keys.** Condition steps use `then`/`else` keys that the
   strict `PresetStep` model does not serialize. A single shared helper
   (`src/ambrosia/presets/normalize.py`) strips them before validation and is
   used by both `PresetLoader` and `PresetService`, so CLI/TUI preset commands
   accept the same documents as the engine.
4. **Artifact persistence is an optional engine dependency.** `JobEngine`
   accepts `artifact_repository=None` for backward compatibility; when
   supplied, `ArtifactProducedEvent` drafts are persisted with provenance.
5. **Datetime import with `noqa: TC003`.** `src/ambrosia/storage/models.py`
   imports `datetime` at runtime because SQLAlchemy resolves `Mapped[datetime]`
   annotations at mapper configuration time. Moving it under `TYPE_CHECKING`
   raises `MappedAnnotationError`.
6. **User presets directory.** `PresetService` discovers presets in the
   configured read-only directories plus a writable workspace-local directory
   (`.ambrosia/presets` by default). Saving forks a preset with a fresh
   namespaced id; existing ids are never silently overwritten.
7. **TUI refresh model.** Views are recreated on navigation and refreshed
   through guarded async callbacks; the dashboard reads the artifact repository
   on refresh rather than receiving a pushed artifact event.
8. **Action availability for Nmap service names.** Follow-up prerequisites
   accept both canonical labels and Nmap's actual service names via an any-of
   matcher; the aliases are declared explicitly in the pack.
9. **Opt-in authorized operations pack (ADR-0012).** A separate pack wraps
   installed Impacket/NetExec/samdump2 binaries through the shell-free argv
   executor. It is never registered by default. Every high-impact run requires
   explicit pack registration, scope effect allowlisting, a per-run
   authorization reference, and engine approval. Raw tool output is not
   persisted unless `show_output: true` is set. The matcher now checks effect
   allowlisting even when an action has no target (offline actions).
10. **Explicit authorization gate.** `AuthorizationService` in
    `policy/authorization.py` is called by `PolicyGateway`, `ActionService`,
    `PresetService.run`, and the TUI adapter; the handler repeats the check at
    execution time. CLI uses `--authorization`; the TUI uses an authorization
    input in action details.

## Frozen safety decisions

- Built-in actions are read-only for the initial pack (effects limited to
  `network_observe` and `local_read`).
- Process execution uses argv arrays with `shell=False` semantics only.
- Secrets are opaque references; no raw secret is persisted or logged.
- Policy validation runs on every execution path (CLI, TUI, preset, plugin in future).
- Third-party code is not loaded into the main process. The JSON-RPC plugin
  protocol is a future capability, not a current contract.

## Change process

Do not rename a shared model or field without updating this document and the
contract tests in `tests/contract/`. Add new core abstractions only with a
documented use case and an ADR in `docs/decisions/`.
