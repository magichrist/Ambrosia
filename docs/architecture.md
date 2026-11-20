# Architecture

Ambrosia v0.x is a **modular monolith**: one Python application with strongly
separated packages. Logical components are not separate services.

## Layers

```
Interfaces (TUI / CLI)
        |
Application services (engagement, action, preset, job, scope, target, report, policy gateway)
        |
Context & artifacts   Registry & resolver   Policy engine
        |                    |                   |
        +--------------------+-------------------+
                             |
                     Workflow / job engine
                             |
                 Executors (native, process, script, future plugin)
                             |
                 Parsers -> artifacts -> context events
                             |
                  SQLite / evidence files
```

## Package boundaries

| Package | Responsibility |
|---|---|
| `domain` | Pydantic domain types, enums, Protocols, errors. No UI/DB/executor imports. |
| `artifacts` | Typed artifact definitions and creation/validation. |
| `context` | Engagement-scoped snapshots and event model. |
| `registry` | Action/pack definitions, manifests, validation, availability matcher. |
| `presets` | `ambrosia/v1` loader, reference grammar, predicates, planner, dry-run. |
| `phases` | User-defined organizational phase catalog. |
| `policy` | Scope matching, effect classification, approvals, decision records. |
| `engine` | Job lifecycle, event stream, durable transitions. |
| `executors` | Native/process/script adapters and tool output parsers. |
| `storage` | SQLAlchemy ORM models, repositories, migrations, evidence index. |
| `application` | Use-case services and DTOs shared by all interfaces. |
| `tui` | Textual presentation only — no business logic, DB, or subprocess calls. |
| `cli` | Thin Typer commands that call application services. |
| `packs` | Built-in domain packs (Windows assessment first). |
| `secrets` | Secret-provider protocol integration point. |

## Dependency direction

Allowed: interfaces → application services → domain/protocols; engines →
domain/registry/executor/policy protocols; storage implements repository
protocols; packs register definitions against stable contracts.

Forbidden: domain → UI/DB/concrete tools; TUI → subprocess or SQLAlchemy;
CLI → direct database queries; presets → arbitrary Python imports or
execution; action handlers → UI mutation; ORM objects escaping storage.

## Key data flows

### Artifact lifecycle

Actions emit `ArtifactProducedEvent` drafts with a typed `value`, `source`,
`source_execution_id`, `target_ref`, `sensitivity`, and `secret_ref` when
needed. The engine persists them and exposes them through the artifact
repository. Artifacts are immutable; changes are represented by superseding
relationships. An artifact discovered on host A does not satisfy a
target-bound prerequisite for host B unless the action explicitly allows it
(`ArtifactRequirement.same_target = False`).

### Execution lifecycle

```
draft -> validated -> awaiting_input | awaiting_approval -> ready
      -> running -> parsing -> succeeded | partial | failed | cancelled | blocked
```

Every transition and event is persisted. Cancellation and timeouts are
explicit; non-idempotent operations are never retried automatically.

### Context and matching

`ContextSnapshot` is a read-only view over the engagement, scope, selected
target, active artifacts, inputs, available tools, and platform. The matcher
evaluates each action against registration, platform, artifact requirements,
dependencies, target/scope, policy and approval, and required inputs. It is
pure: identical snapshots produce identical results.

## Runtime integration

- `ambrosia.registry.loader.build_registry()` builds the production registry
  and registers the built-in Windows pack. It is used by both CLI and TUI.
- `ambrosia.application.services.load_services()` wires repositories,
  services, and the optional job engine. It re-registers built-ins on bare
  registries (guarded and idempotent).
- `PresetService` loads presets from configured directories plus the writable
  workspace presets directory; saved presets are immediately discoverable.
- Long work runs in asyncio/Textual workers; the UI event loop is never blocked.

## Extension model

Today, built-in actions are trusted Python code registered by packs. The
future M7 model uses a versioned JSON-RPC subprocess protocol so that a
third-party plugin failure cannot crash the core and all plugin requests pass
through the same policy and scope checks. See `plugin-development.md`.
