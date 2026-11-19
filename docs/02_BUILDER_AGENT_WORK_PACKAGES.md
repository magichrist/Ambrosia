# Ambrosia — Builder Agent Work Packages

This document contains ready-to-assign briefs for builder agents. The project should use one lead/integrator and a set of specialist agents. Agents must not independently redesign shared contracts.

## 0. Rules for every builder agent

Every agent receives:

- `00_MASTER_PLAN.md`
- `01_SHARED_CONTRACTS.md`
- its specific work package below

Every agent must:

1. Read both shared documents before editing code.
2. Inspect the existing repository and report its current state before changing it.
3. Work only in its assigned paths unless the lead approves an exception.
4. Reuse shared public contracts. Do not invent alternative versions of `Artifact`, `ActionDefinition`, `PresetDefinition`, or `ExecutionRecord`.
5. Add tests with implementation, not afterward.
6. Keep code typed, documented, and formatted.
7. Use fixtures and fake executors; tests must not require a live target or real external security tools.
8. Never place real credentials, hashes, tokens, keys, or customer data in fixtures.
9. Report changed files, commands run, test results, open issues, and exact integration requirements.
10. Do not claim completion if tests were not run.

Suggested collaboration method: one branch/worktree per agent, then lead integrates. If the environment supports shared worktrees, use them. Avoid concurrent edits to common files.

---

# Agent 0 — Lead Architect and Integrator

**Priority:** First and continuous  
**Owns:** root project structure, architecture decisions, shared contracts, integration, release gates  
**Primary paths:** `docs/`, `pyproject.toml`, `README.md`, `src/ambrosia/__init__.py`, `src/ambrosia/domain/contracts/`  
**Must not:** implement all subsystems itself or let agents redefine shared contracts independently.

### Prompt for Agent 0

You are the lead architect and integration engineer for Ambrosia, a Python context-driven automation workbench. Read `00_MASTER_PLAN.md` and `01_SHARED_CONTRACTS.md` fully.

Your tasks:

1. Inspect the repository and produce a concise architecture/status report.
2. Create the Python project skeleton using Poetry and a `src/` layout.
3. Establish the selected Python version floor, package metadata, `ambrosia` CLI entry point placeholder, Ruff, test configuration, and type-check configuration.
4. Create the initial public contract package for shared domain types and protocols, following `01_SHARED_CONTRACTS.md`.
5. Write architecture decision records for:
   - modular monolith for v0.x
   - domain/application/infrastructure boundaries
   - Textual + Typer sharing application services
   - typed artifacts and context matching
   - declarative presets and strict variable references
   - trusted in-process built-ins versus process-isolated third-party extensions
   - safe process execution and scope enforcement
6. Freeze public interfaces before delegating parallel implementation. Create a contract version or changelog so agents know when a contract changes.
7. Create a lightweight integration test harness and common fixtures.
8. Integrate the specialist agents' branches, resolve conflicts, run the full suite, and update docs.

Acceptance criteria:

- `poetry install` works in a clean environment.
- `poetry run ambrosia --help` works, even if only placeholder commands exist.
- `poetry run pytest` discovers and runs the baseline suite.
- `poetry run ruff check .` and formatter checks pass.
- Domain contract imports do not import Textual, Typer, or SQLAlchemy.
- Public contracts are documented and all specialist agents can import them.
- A short integration report lists merged work, test results, and remaining blockers.

Do not add actual offensive modules. The initial release is a read-only assessment and general automation foundation.

---

# Agent 1 — Domain Models, Artifacts, and Context Store

**Priority:** Stage 1  
**Owns:** `src/ambrosia/domain/`, `src/ambrosia/context/`, `src/ambrosia/artifacts/`  
**Depends on:** Agent 0 freezing common types/protocols  
**Must not:** create SQLAlchemy tables, build TUI screens, or execute external commands.

### Prompt for Agent 1

Implement Ambrosia's domain model, typed artifact system, and engagement context service. Read both shared documents.

Responsibilities:

1. Implement validated domain types for engagement, target, scope, artifact, execution state, observations, and findings.
2. Implement artifact type definitions for the first vertical slice:
   - `network.host`
   - `network.service`
   - `windows.domain`
   - `windows.host_role`
   - `identity.user_ref`
   - `secret.ref` (metadata/reference only; no secret value)
   - `evidence.ref`
   - `observation`
   - `finding`
3. Implement artifact creation validation, provenance, sensitivity labels, target binding, supersession, and expiry metadata.
4. Implement an engagement-scoped context service that queries repositories through protocols. Do not duplicate every artifact in a mutable arbitrary dictionary.
5. Implement context snapshots or query models that expose the namespaces defined in `01_SHARED_CONTRACTS.md`.
6. Implement derived facts with source artifact IDs and target provenance.
7. Implement context events for target/artifact/execution changes.
8. Add pure helper functions for determining which artifacts belong to a target or scope.
9. Ensure that artifacts from one host cannot accidentally satisfy requirements for another host unless the action explicitly declares that cross-target use is valid.
10. Ensure all secret values are excluded from `model_dump`, `repr`, and normal logs. Only opaque references are allowed in domain artifacts.

Tests required:

- valid/invalid artifact types and payloads
- provenance survives serialization
- target scoping prevents cross-host artifact matches
- secret reference redaction
- artifact supersession and expiry behavior
- context snapshot consistency
- context event serialization

Acceptance criteria:

- domain package has no imports from storage/TUI/CLI/executors
- no raw credential material is represented in stored artifacts
- model validation errors are clear and stable
- unit tests pass without database or network

---

# Agent 2 — Storage, Repositories, and Migrations

**Priority:** Stage 1  
**Owns:** `src/ambrosia/storage/`, `alembic/`, storage tests  
**Depends on:** Agent 0 contracts; Agent 1 domain models  
**Must not:** put business logic in ORM models or import ORM entities into UI/domain packages.

### Prompt for Agent 2

Implement SQLite persistence with SQLAlchemy 2.x and Alembic. Read the master plan and shared contracts.

Responsibilities:

1. Create SQLAlchemy ORM models for engagement, scope, target, artifact, execution, execution event, finding, approval record, and evidence metadata.
2. Implement repository classes matching the protocols in `01_SHARED_CONTRACTS.md`.
3. Convert ORM rows to domain models at repository boundaries. ORM instances must never escape the storage package.
4. Create Alembic initial migration and migration test.
5. Support workspace-local DB paths and an in-memory SQLite option for tests.
6. Configure foreign keys, indexes, uniqueness constraints, and transactions.
7. Store timestamps consistently in UTC.
8. Store structured JSON with validated serialization. Never store secret values in DB columns.
9. Store evidence files under generated IDs in a controlled application data directory; DB stores metadata and the generated relative path.
10. Add backup/export hooks for an engagement bundle, without exporting secret values.

Tests required:

- repository CRUD and relationship behavior
- rollback on failed transaction
- foreign-key enforcement
- engagement isolation
- migration from empty DB to current schema
- evidence metadata/content hash round trip
- serialization of typed domain models
- no ORM model leakage from repository APIs

Acceptance criteria:

- repository implementations satisfy shared protocols
- `alembic upgrade head` creates a valid DB
- test suite works with a temporary DB
- storage layer never logs or stores plaintext secret values
- migrations are reproducible and checked into source control

---

# Agent 3 — Action Registry, Manifests, and Availability Matcher

**Priority:** Stage 1  
**Owns:** `src/ambrosia/registry/`, `src/ambrosia/actions/`, registry tests  
**Depends on:** Agent 0 contracts; Agent 1 artifact/context interfaces  
**Must not:** execute commands or build the UI.

### Prompt for Agent 3

Build the action registry and pure action-availability matcher. Read the master plan and shared contracts.

Responsibilities:

1. Implement action definition loading from built-in Python definitions and safe manifest files.
2. Validate action IDs, versions, schemas, executor references, output types, dependency declarations, effects, and duplicate IDs.
3. Implement registry operations: register, get, list, search, filter by category/tag/platform, and pack enable/disable.
4. Implement tool dependency checks as metadata checks only; do not run tools during registry import.
5. Implement `ActionAvailability` evaluation using a read-only context snapshot and policy snapshot.
6. Implement clear missing-input, missing-artifact, blocked-by-scope, missing-dependency, and approval-required reasons.
7. Ensure matching has no side effects and is deterministic for a fixed input snapshot.
8. Implement pack loading and duplicate/conflict reporting.
9. Support user-defined phase references as metadata, without making phase state a mandatory execution lifecycle.
10. Provide a built-in `core.echo`/diagnostic action for end-to-end tests only.

Tests required:

- manifest schema validation
- duplicate action and pack IDs
- missing handler/dependency handling
- action availability for each status
- deterministic matching
- target-scoped artifact requirements
- phase references do not control action eligibility
- registry listing/search/filter behavior

Acceptance criteria:

- registry can load a test pack from fixtures
- matcher explains why an action is suggested or unavailable
- no action executes as a side effect of registration or discovery

---

# Agent 4 — Preset System, Variable Resolver, and Phase Definitions

**Priority:** Stage 2  
**Owns:** `src/ambrosia/presets/`, `src/ambrosia/phases/`, preset schemas and tests  
**Depends on:** Agent 0 contracts; Agent 1 artifact/context types; Agent 3 action registry  
**Must not:** implement arbitrary Python expressions or call executors directly.

### Prompt for Agent 4

Implement Ambrosia's declarative preset and phase system. Presets are reusable action/workflow definitions; phases are user-defined organizational labels. Read the shared contracts carefully.

Responsibilities:

1. Define Pydantic schemas for `ambrosia/v1` preset documents and phase documents.
2. Load YAML safely. Reject Python object tags, unknown/invalid fields, duplicate step IDs, unresolved action IDs, cyclic dependencies, and invalid references.
3. Implement variable reference parsing for the exact namespaces in `01_SHARED_CONTRACTS.md`.
4. Resolve values as typed objects, not arbitrary strings. Missing inputs should return a structured `InputRequest`; ambiguous artifacts should return an `ArtifactSelectionRequest`.
5. Resolve secrets only to opaque secret handles. Never reveal secret values to the preset engine, preview renderer, or logger unless a specific executor requires a protected handle through the secret provider.
6. Implement step dependency validation and a deterministic plan representation.
7. Implement initial step types: action, condition, approval, output.
8. Implement a constrained predicate grammar (e.g. artifact exists, artifact field equals an enumerated literal, input is present). No `eval`, arbitrary expressions, imports, loops, or unrestricted Jinja.
9. Implement preset-level effect summary by taking the union of step effects.
10. Implement phase loading and listing. A phase may group actions/presets and define display metadata; it cannot grant permission or force lifecycle order.
11. Add preset validation and dry-run plan generation without executing actions.
12. Add schema docs and example presets.

Tests required:

- valid/invalid YAML
- duplicate/cyclic step graphs
- all supported reference namespaces
- missing and ambiguous variable resolution
- type mismatch handling
- secret redaction
- constrained predicate behavior
- phase is organizational only
- dry-run is deterministic and never invokes an executor

Acceptance criteria:

- a sample discovery preset validates and produces a deterministic plan
- no arbitrary code can execute from YAML
- missing user inputs can be surfaced to the TUI/CLI in a typed form

---

# Agent 5 — Policy Engine, Job Engine, and Executors

**Priority:** Stage 2  
**Owns:** `src/ambrosia/policy/`, `src/ambrosia/engine/`, `src/ambrosia/executors/`  
**Depends on:** Agents 0–4 contracts and protocols  
**Must not:** call Textual widgets, bypass scope, or build domain-specific exploit behavior.

### Prompt for Agent 5

Implement the policy validation layer, job lifecycle, workflow scheduler, and safe execution interfaces for Ambrosia. Read both shared documents.

Responsibilities:

1. Implement scope matching for exact IPs, CIDRs, hostnames/domains, exclusions, allowed ports, expiry, and engagement binding.
2. Ensure every action execution validates all target values after variable resolution and before starting any process.
3. Implement effect classification and policy decision records.
4. Implement approval state for actions requiring approval; v0.1 may use a CLI/TUI confirmation service, but the engine must represent approval as an explicit state transition.
5. Implement execution lifecycle and event stream. Every job has an ID and durable status transitions.
6. Implement concurrency limits, timeouts, cancellation, output caps, and child-process reaping.
7. Implement a `ProcessExecutor` using `asyncio.create_subprocess_exec` with `shell=False` semantics and argv arrays only.
8. Validate executable ID/name against an action's registered dependency/allowlist. Do not execute an arbitrary command path supplied through an untrusted preset.
9. Implement process stdout/stderr streaming with secret redaction and output size limits.
10. Implement cancellation on operator request and timeout; make sure the child process is terminated/reaped.
11. Implement dry-run that resolves inputs and displays a sanitized execution plan but launches no process.
12. Implement a fake executor for tests.
13. Do not add built-in credential extraction, hash replay, password spraying, persistence, evasion, exfiltration, or remote command execution features.

Tests required:

- scope include/exclude behavior, DNS resolution boundary, expiry
- target outside scope blocked on every path
- policy effects and approval transitions
- argv preserved as separate arguments
- shell metacharacters passed as data, not interpreted
- timeout and cancellation terminate subprocess
- output cap works
- secret redaction in stdout/stderr/logs/previews
- dry-run does not start subprocess
- concurrent job limit works

Acceptance criteria:

- no network executor can launch without a valid scope check
- subprocess execution is shell-free
- execution lifecycle is persisted through repository protocols
- all process tests use harmless local fixtures/fake programs

---

# Agent 6 — Adaptive Textual TUI

**Priority:** Stage 3  
**Owns:** `src/ambrosia/tui/`, TUI tests  
**Depends on:** application service interfaces from Agents 0–5  
**Must not:** perform business logic, query SQLAlchemy directly, or launch subprocesses directly.

### Prompt for Agent 6

Implement Ambrosia's adaptive Textual terminal interface. This is not a fixed phase-menu application. The screen content should react to the current engagement context, available actions, artifacts, and running jobs. Read the master plan and shared contracts.

Responsibilities:

1. Build a persistent workspace shell with status bar, context rail, primary content area, activity timeline, and global command palette.
2. Implement engagement selection/creation, target/scope view, action search, action details, input collection, preset browser, job monitor, artifact browser, and findings/evidence views.
3. Show recommended actions based on the `ActionAvailability` service result.
4. Explain why an action is suggested, unavailable, blocked, missing inputs, or missing dependencies.
5. Do not hide unavailable actions from global search; show their state and reason.
6. When an action completes and context changes, refresh suggestions without dumping the user back to a fixed main menu.
7. Preserve navigation state and current target/engagement while moving between views.
8. Run long operations via Textual workers or application job services; the UI must remain responsive.
9. Support viewing streamed logs/progress, cancellation, timeout/failure states, and sanitized execution previews.
10. Use stable keyboard conventions and document them.
11. Build empty, error, loading, and narrow-terminal states.
12. Add Textual pilot tests or equivalent screen/event tests for core interactions.

Suggested keyboard behavior:

- `/`: global search/command palette
- `Tab`: move between context, content, and activity regions
- `Enter`: open/select
- `Esc`: back/close modal
- `g`: engagement/context switcher (optional)
- `?`: help
- `q`: quit, with confirmation if jobs are active

Acceptance criteria:

- TUI loads an engagement and reflects its context
- newly produced artifacts cause relevant action suggestions to appear
- a blocked action explains why
- action execution runs in a worker and does not freeze UI
- user can inspect execution history and artifacts
- no direct DB or subprocess calls exist in TUI package

---

# Agent 7 — CLI, Application Services, and User Workflows

**Priority:** Stage 3  
**Owns:** `src/ambrosia/cli/`, `src/ambrosia/application/`, CLI/service tests  
**Depends on:** stable domain, registry, preset, policy, and repository contracts  
**Must not:** duplicate TUI logic or put core logic in Typer callbacks.

### Prompt for Agent 7

Implement the application-service layer and Typer CLI for Ambrosia. The CLI and TUI must share the same use cases.

Responsibilities:

1. Implement application services for engagement create/list/open, scope display/update, target add/list, action list/info/check, preset list/validate/plan/run, jobs list/show/cancel, and report export.
2. Keep Typer callbacks thin: parse CLI arguments, call an application service, format result, return exit code.
3. Support human-readable output and stable `--output json` for automation.
4. Add `ambrosia` entry point and `python -m ambrosia` support.
5. Ensure all execution paths call the same policy and execution engine as the TUI.
6. Add clear exit codes for validation, scope violations, policy block, missing dependencies, execution failure, and cancellation.
7. Add helpful usage examples and command completion if practical.
8. Do not add direct SQLAlchemy queries inside CLI commands.

Tests required:

- command invocation and help output
- application service behavior with fake repositories
- JSON output schema stability
- exit codes on policy/validation/execution failure
- CLI and TUI invoke the same application service path

Acceptance criteria:

- `ambrosia --help` works
- core engagement/scope/action/preset/job commands work
- `--output json` is valid JSON and stable
- CLI cannot bypass policy validation

---

# Agent 8 — First Windows Assessment Pack and Tool Adapters

**Priority:** Stage 4, after shared engine is integrated  
**Owns:** `src/ambrosia/packs/windows_assessment/`, `src/ambrosia/executors/adapters/`, pack fixtures and tests  
**Depends on:** Agents 1–5 integration and scope/policy contracts  
**Must not:** implement exploit chains, credential theft/replay, persistence, evasion, or remote command execution.

### Prompt for Agent 8

Create the first Windows assessment pack for Ambrosia. Its purpose is read-only discovery and configuration assessment in explicitly authorized environments. Read both shared documents.

Responsibilities:

1. Add pack manifest and action definitions for a small first set:
   - network service discovery (Nmap adapter, bounded targets/ports)
   - SMB service identification/configuration inventory (read-only)
   - LDAP service/domain inventory (read-only)
   - HTTP method/configuration observation (non-mutating; no upload testing)
   - RDP exposure/configuration observation
   - WinRM exposure/configuration observation
2. Prefer machine-readable formats such as Nmap XML. Do not parse human-formatted tables when a structured format exists.
3. Implement parsers that produce typed `network.service`, `windows.domain`, `windows.host_role`, and `observation` artifacts.
4. Check local tool availability and version without running assessments during pack registration.
5. Use fixtures for tool output and parser tests.
6. Add remediation guidance as text metadata only; do not automatically modify target settings.
7. Ensure each network action declares target fields and scope requirements.
8. Add examples showing how discovered SMB/LDAP/HTTP/RDP artifacts cause further actions to be suggested.
9. Include explicit limitations in module docs. For example, advertised HTTP methods are observations and do not prove exploitability.
10. Keep credential material out of the initial built-in pack. Authentication-dependent modules require separate review.

Tests required:

- pack loads and validates
- parsers handle expected and malformed fixtures
- action metadata declares effects, target fields, and dependencies
- action matching after generated artifacts
- modules can run in dry-run with no external tools installed
- network modules refuse targets outside scope

Acceptance criteria:

- at least one discovery action runs end-to-end in a lab or with a fake executor
- tool output becomes typed artifacts
- resulting artifacts change the suggested action list
- no target-modifying behavior exists in the initial pack

---

# Agent 9 — QA, Documentation, and Release Hardening

**Priority:** Parallel after Stage 1; final gate at Stage 6  
**Owns:** `tests/` cross-package suites, `docs/user/`, `docs/developer/`, release checklist  
**Depends on:** all agents' declared public APIs  
**Must not:** change production contracts without lead approval.

### Prompt for Agent 9

Act as Ambrosia's QA and documentation engineer. Your goal is to verify the product as an integrated system, not just unit-test individual functions.

Responsibilities:

1. Build end-to-end test scenarios using temporary SQLite DBs and fake executors.
2. Test the complete loop: engagement -> scope -> target -> action -> execution -> parser -> artifact -> context update -> action suggestion -> preset save/validate -> report.
3. Test CLI and TUI service parity.
4. Add tests for invalid presets, unknown actions, missing dependencies, policy blocks, process timeout, cancellation, malformed output, and DB recovery.
5. Verify all logs/reports/errors/CLI output are secret-safe.
6. Add developer docs for action authoring, preset authoring, pack authoring, phase authoring, and parser authoring.
7. Add operator docs for creating engagements, scopes, targets, running actions, saving presets, and exporting evidence.
8. Add a troubleshooting guide for tool dependencies and common failures.
9. Prepare release checklist, packaging smoke tests, supported OS matrix, and changelog.
10. Run tests in a clean install, not only an existing developer environment.

Acceptance criteria:

- complete vertical slice test passes without a live network
- release install works in clean virtual environment
- no secrets appear in test logs or generated reports
- documentation examples validate against actual schemas
- outstanding issues are categorized by severity

---

## 11. Recommended assignment order

Do not start all agents simultaneously. Use these dependency gates:

### Wave 0 — Contract freeze

- Agent 0 creates the skeleton, shared contracts, error model, and repository protocols.
- Agent 9 reviews contract testability and asks for missing cases.

### Wave 1 — Core foundation (parallel)

- Agent 1: domain/artifacts/context
- Agent 2: storage/repositories
- Agent 3: registry/action matching

Agent 0 integrates and resolves contract gaps. Agent 4 can start schemas against frozen examples but should not invent new domain fields.

### Wave 2 — Execution model (parallel where safe)

- Agent 4: presets/resolver/planner
- Agent 5: policy/job/executor
- Agent 7: application services/CLI skeleton

Agents 4 and 5 must agree on the execution plan/request contracts before integration.

### Wave 3 — User experience

- Agent 6: TUI against application service protocols
- Agent 7: complete CLI and services
- Agent 9: integration scenarios and documentation scaffolding

### Wave 4 — First domain pack

- Agent 8: Windows read-only pack and Nmap parser/adapter
- Agent 9: vertical slice tests and operator docs

### Wave 5 — Integration and release

- Agent 0 integrates all work.
- Agent 9 performs release hardening.
- All agents fix integration defects in their owned paths.

## 12. Agent handoff format

Every agent must finish with this report:

```text
WORK PACKAGE: <agent id and name>
STATUS: complete | partial | blocked

FILES ADDED/CHANGED:
- ...

PUBLIC INTERFACES ADDED:
- ...

TESTS RUN:
- command: ...
- result: ...

DEPENDENCIES / ASSUMPTIONS:
- ...

KNOWN LIMITATIONS:
- ...

INTEGRATION NOTES FOR LEAD:
- ...

NEXT RECOMMENDED TASK:
- ...
```

A work package is not complete if it only creates file stubs or untested interfaces.
