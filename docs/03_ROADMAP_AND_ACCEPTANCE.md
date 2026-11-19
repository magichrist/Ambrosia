# Ambrosia — Roadmap, Milestones, and Acceptance Tests

## 1. Release roadmap

### Milestone M0 — Repo and contract freeze

Deliverables:
- Poetry project, `src/` layout, `ambrosia` entry point.
- Ruff, pytest, selected type checker, CI workflow.
- Domain contract package and architecture decision records.
- Initial test fixtures and fake executor protocol.

Exit criteria:
- Clean install works.
- Shared contracts import without UI/storage dependencies.
- `ambrosia --help`, `pytest`, and lint commands work.

### Milestone M1 — Context and artifact foundation

Deliverables:
- Engagement, scope, target, artifact, execution, observation, finding models.
- Typed artifact registry.
- Provenance and target binding.
- Context snapshots and event model.
- SQLite repositories and Alembic migration.

Exit criteria:
- Artifacts are persisted and reconstructed without losing provenance.
- Cross-target artifact matching is blocked by default.
- Secret material is not stored in artifacts.

### Milestone M2 — Action registry and availability

Deliverables:
- Action definitions and built-in registry.
- Pack manifest loader.
- Dependency metadata.
- Pure action matcher.
- Action availability explanations.

Exit criteria:
- Registry loads test packs and reports duplicate/invalid entries.
- Action suggestions are explainable and deterministic.
- Registry loading performs no action execution.

### Milestone M3 — Presets, resolver, and planning

Deliverables:
- `ambrosia/v1` preset schema.
- Safe YAML loader.
- Typed variable resolver.
- Step graph validation.
- Dry-run execution plan.
- User-defined phase metadata.

Exit criteria:
- Sample preset validates.
- Missing inputs are returned as structured requests.
- No arbitrary Python or shell code is evaluated from YAML.
- Dry-run starts no external process.

### Milestone M4 — Policy and execution

Deliverables:
- Scope validator.
- Effect classifier.
- Approval model.
- Job lifecycle and event stream.
- Process executor with argv arrays, timeout, output cap, cancellation.

Exit criteria:
- Out-of-scope target cannot run through CLI, TUI, or preset.
- Timeout/cancellation terminates and reaps child process.
- Command arguments remain separate argv values.
- Secret redaction passes tests.

### Milestone M5 — CLI and adaptive TUI

Deliverables:
- Typer commands backed by application services.
- Textual workspace shell.
- Context rail, action suggestions, global search, action details, preset browser, job monitor.
- TUI updates after artifact/context events.

Exit criteria:
- TUI never freezes during job execution.
- The same use case works from CLI and TUI.
- Newly discovered service artifacts update suggested actions without a full application restart.

### Milestone M6 — First Windows pack and vertical slice

Deliverables:
- Nmap service discovery adapter/parser.
- Read-only SMB/LDAP/HTTP/RDP/WinRM assessment metadata and safe modules where dependencies permit.
- Example pack and presets.
- Evidence export.

Exit criteria:
- Full end-to-end demo and integration tests pass.
- No state-changing built-in action is included in the first Windows pack.
- User can save a successful workflow as a reusable preset.

### Milestone M7 — Extension ecosystem (later)

Deliverables:
- JSON-RPC subprocess plugin protocol.
- Pack installation/removal and trust metadata.
- Plugin compatibility checks and capability declarations.
- Developer SDK and sample extension.

Exit criteria:
- External plugin failure cannot crash the core process.
- Plugin requests pass through policy and scope checks.
- Plugin outputs are schema-validated.

## 2. Critical acceptance scenarios

### Scenario A — New engagement

Given a fresh workspace:
- create engagement `lab-windows`
- define a narrow scope
- add one target
- inspect the target context

Expect:
- engagement persists after restart
- target appears in context
- no network action is available until scope is explicitly defined

### Scenario B — Discovery changes the UI

Given an in-scope target and discovery action:
- run discovery via fake executor fixture
- parser returns SMB and RDP service artifacts

Expect:
- artifacts are persisted
- their target provenance is retained
- action matcher suggests applicable SMB and RDP assessment actions
- UI refreshes current action suggestions
- each suggestion explains which artifact made it applicable

### Scenario C — Preset variable resolution

Given a preset that requires a target and port list:
- target exists in context
- ports are not provided

Expect:
- resolver binds target from context
- UI/CLI requests ports using a typed input prompt
- invalid port values are rejected before execution
- resolved plan displays a sanitized preview

### Scenario D — Scope cannot be bypassed

Given a preset step whose target variable resolves outside the engagement scope:

Expect:
- plan/execution is blocked
- no process is launched
- a policy decision record is saved
- operator sees the reason and the mismatching target

### Scenario E — Context provenance prevents accidental cross-target reuse

Given artifact A discovered on host 10.0.0.10 and action targeting 10.0.0.20:

Expect:
- artifact A does not satisfy target-specific prerequisites for 10.0.0.20 unless the action schema explicitly allows cross-target artifacts

### Scenario F — Execution cancellation

Given a long-running fake process:
- start job
- cancel job from TUI or CLI

Expect:
- child is terminated and reaped
- execution becomes `cancelled`
- final output and cancellation event are persisted
- UI remains responsive

### Scenario G — Secret hygiene

Given a secret reference used as a protected input:

Expect:
- raw secret is not shown in input preview
- raw secret is not persisted in SQLite
- raw secret does not appear in logs/errors/reports
- executor receives only the minimum required protected handle/value

### Scenario H — Custom phases do not dictate workflow

Given user-defined phases `before-auth`, `after-auth`, and `inventory`:

Expect:
- actions can belong to one or more phases
- changing phase selection does not mutate context or grant access
- an applicable action remains discoverable from global search even if not in the selected phase

## 3. Non-functional requirements

- Startup: display a useful interface promptly with no mandatory network calls.
- Responsiveness: long jobs run outside the UI event loop.
- Reliability: all job state transitions are persisted.
- Recoverability: interrupted jobs are identified on next startup as interrupted/unknown, not silently marked successful.
- Portability: core should run on Linux, macOS, and Windows where dependencies permit. Document platform-specific tool limitations.
- Determinism: preset validation and dry-run planning are deterministic for the same inputs and registry version.
- Extensibility: packs can be added without editing core engine code.
- Auditability: every execution has an operator, engagement, action/preset ID, resolved safe input summary, scope decision, timestamps, result, and artifact references.

## 4. CI pipeline

Every pull request should run:

1. Ruff lint.
2. Ruff format check.
3. Static type check.
4. Unit tests.
5. Contract tests.
6. TUI smoke tests.
7. Dependency audit (when configured).
8. Build wheel and sdist.
9. CLI help smoke test from installed package.

Nightly or release CI may run the broader OS matrix and optional integration tests with local fake tools.

## 5. Release checklist

- [ ] Clean Poetry install works.
- [ ] Wheel and sdist build.
- [ ] `ambrosia --help` and `python -m ambrosia --help` work.
- [ ] Database migration from empty DB works.
- [ ] Database migration from previous release works.
- [ ] Built-in pack and sample presets validate.
- [ ] Full vertical-slice scenario passes.
- [ ] Scope enforcement tests pass on all execution paths.
- [ ] Process timeout/cancellation tests pass.
- [ ] Secret redaction tests pass.
- [ ] Documentation examples are tested or validated.
- [ ] No real credentials or engagement data are committed.
- [ ] Changelog and known limitations are updated.
