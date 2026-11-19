# Ambrosia — Master Builder Plan

**Project:** Ambrosia  
**Product type:** Context-driven automation workbench, initially focused on authorized Windows and Active Directory security assessment  
**Implementation language:** Python  
**Primary interface:** Adaptive terminal UI  
**Status:** Initial implementation plan  

---

## 1. Product vision

Ambrosia is a context-driven automation workbench. It is not a fixed checklist, a conventional command wrapper, or a rigid penetration-testing wizard.

The operator works in an engagement or workspace. As actions run, Ambrosia collects typed artifacts, updates the current context, and changes the operations it recommends or makes available. The operator remains in control and can choose a recommended action, search for another action, run a preset, or define a custom preset.

The core must be domain-independent. Windows and Active Directory assessment is the first domain pack, not a hard-coded limitation. The same engine should eventually support network inventory, web assessment, Linux administration, incident-response collection, and ordinary operations automation.

### Product statement

> Ambrosia turns operator knowledge, tools, scripts, and commands into reusable, typed, context-aware actions and presets.

### The key interaction loop

1. Operator selects or creates an engagement.
2. Operator defines the authorized scope and initial context.
3. Ambrosia displays actions that are relevant and currently usable.
4. Operator selects an action or preset.
5. Ambrosia resolves typed inputs from the user, context, artifacts, and secret references.
6. Policy validates the action and its effects.
7. The execution engine runs the action and streams progress.
8. Parsers turn outputs into typed artifacts and observations.
9. The context is updated and the action matcher recalculates available operations.
10. The UI changes to reflect the new context.

The UI should feel continuous. It should not force the operator back to a static main menu after each action.

---

## 2. Terminology — freeze these definitions

Use these words consistently in code, docs, manifests, and UI.

| Term | Definition |
|---|---|
| **Workspace** | A local Ambrosia data boundary containing configuration, packs, and one or more engagements. |
| **Engagement** | A named unit of work with its own scope, targets, context, artifacts, executions, and findings. It may represent a pentest, lab, audit, or general automation job. |
| **Scope** | The explicit authorization boundary: included targets, exclusions, permitted protocols/ports, limits, expiration, and approval rules. |
| **Context** | The current engagement state derived from operator inputs, target inventory, artifacts, execution results, and user decisions. |
| **Artifact** | A typed item of information produced, imported, or confirmed during work. Examples: host, service, domain, identity reference, credential reference, session reference, file reference, observation, or finding. |
| **Action** | The smallest reusable operation. An action has metadata, typed inputs, requirements, an executor, output parsers, and declared effects. |
| **Preset** | A reusable, declarative collection of action steps, variable bindings, conditions, and presentation metadata. A preset may be a single command or a multi-step workflow. |
| **Phase** | A user-defined label/grouping for organizing actions and presets. A phase is not a hard-coded lifecycle state and does not dictate the next step. |
| **Pack** | A distributable collection of actions, schemas, presets, phases, and documentation for a domain such as Windows or Active Directory. |
| **Resolver** | The component that resolves typed references from user inputs, context, artifacts, prior step outputs, defaults, and secret stores. |
| **Execution** | One attempt to run an action or preset. It has a lifecycle, job ID, logs, outputs, status, cancellation, and provenance. |
| **Observation** | A technical fact or raw assessment result that has not necessarily been judged to be a vulnerability. |
| **Finding** | A validated security issue or policy deviation with evidence, impact, and remediation guidance. |

### Important distinction

- **Context determines applicability.**
- **Phases organize the operator's view.**
- **Presets define repeatable sequences.**
- **Actions perform work.**
- **Artifacts connect the results of one action to another.**

Do not implement these as synonyms.

---

## 3. Product principles and non-negotiables

1. **Context-driven, not menu-driven.** The current screen is shaped by engagement context and applicable capabilities.
2. **Operator-directed.** Ambrosia recommends and explains; it does not silently choose high-impact next steps.
3. **Everything reusable.** Individual actions, presets, phases, packs, and output parsers must be independently reusable.
4. **Typed data flow.** Outputs become typed artifacts, not undocumented strings copied between commands.
5. **No hard-coded pentest lifecycle.** Windows/AD phases are supplied by packs or users.
6. **CLI and TUI share services.** The interface must never contain business logic or direct tool-execution logic.
7. **Safe by default.** Every network action declares its target fields and effects. Scope is checked at execution time, not only when the user creates a target.
8. **Secrets are references.** Passwords, tokens, keys, and credential material must not be persisted in plaintext database rows, YAML, logs, or command previews.
9. **Extensibility without arbitrary in-process code loading.** Built-in actions may be Python implementations. Third-party extensions should use a versioned process boundary; installed Python entry points are trusted-code extensions only.
10. **MVP before framework sprawl.** First prove one complete path from target input to discovery, normalized artifacts, context update, dynamic action suggestions, and evidence persistence.
11. **Deterministic, inspectable execution.** The user can preview resolved inputs, see which preset step is running, inspect provenance, and reproduce the execution.
12. **No hidden side effects.** Actions declare whether they are read-only, locally modifying, remotely modifying, or otherwise state-changing. Unknown effects are not silently accepted.

### Initial safety boundary

The initial implementation is for authorized assessment and general-purpose, policy-governed automation. The first Windows pack should prioritize inventory and read-only configuration checks. Do not implement credential dumping, hash replay, unauthorized remote command execution, persistence, stealth/evasion, destructive actions, or data exfiltration as built-in actions. The artifact and secret-reference model may represent sensitive information safely, but that does not make every operation using it an approved capability. Add high-impact capabilities only through a separately reviewed design, explicit authorization requirements, and a documented safety case.

---

## 4. Target user experience

### 4.1 Adaptive workspace

Keep a stable outer frame, but let its content change with context.

Recommended layout:

- **Top/status bar:** Ambrosia, engagement name, scope status, current target/context, running jobs.
- **Context rail:** selected target, known domains, discovered services, artifacts, identity references, active sessions, last action.
- **Main workspace:** context-relevant actions, action details, preset options, current result, or workflow view.
- **Activity/timeline panel:** recent actions, execution progress, generated artifacts, warnings, and policy decisions.
- **Command palette:** global search for actions, presets, phases, artifacts, targets, and commands.

Do not create one permanent screen for every possible pentest phase. Use Textual screens or contextual panels for views, but preserve the current engagement context when navigating.

### 4.2 Adaptive behavior example

1. User adds an in-scope host.
2. A discovery action identifies SMB, LDAP, HTTP, and RDP services.
3. The parser creates `service.endpoint` artifacts.
4. The context matcher detects those artifacts.
5. The UI surfaces applicable SMB, LDAP, HTTP, and RDP assessment actions.
6. An SMB inventory action identifies a domain name and server role.
7. New domain-related actions become applicable.
8. The operator can inspect, run, save, or ignore those suggestions.

The application must explain **why** each action is suggested and, when unavailable, list missing requirements. Search must still expose all registered actions, with clear availability status.

### 4.3 Dynamic action states

Each action shown to the user should be in one of these states:

- `available`: all required inputs and context conditions are satisfied.
- `needs_input`: applicable, but one or more user inputs are missing.
- `needs_approval`: applicable, but policy requires operator approval.
- `blocked`: scope or policy prohibits execution; show the reason.
- `missing_dependency`: required local tool, pack, or runtime is unavailable.
- `not_applicable`: required context is absent; explain what would make it applicable.

Do not hide blocked actions without explanation.

---

## 5. Recommended Python stack

Use a conservative, well-supported Python stack. Pin compatible version ranges in `pyproject.toml` and commit the lock file. Do not hard-code a dependency version from this planning document; the integration agent should resolve current compatible releases when bootstrapping.

| Concern | Choice | Responsibility |
|---|---|---|
| Runtime | Python 3.12+ | Baseline runtime, broad library compatibility |
| TUI | Textual | Screens, widgets, reactive presentation, keyboard interaction, background workers |
| CLI | Typer | Headless commands and automation interface |
| Validation | Pydantic v2 | Validate manifests, settings, action inputs, event payloads |
| Settings | pydantic-settings | Environment and local configuration |
| Database | SQLite + SQLAlchemy 2.x | Persistent engagement and execution state |
| Migrations | Alembic | Versioned schema migrations |
| Async jobs | asyncio | Async execution and job lifecycle |
| YAML | PyYAML `safe_load` or a safe equivalent | Declarative preset and pack loading |
| Template resolution | Ambrosia-owned typed resolver | Strict variable binding; no arbitrary template evaluation |
| Logging | standard `logging` or structlog | Structured logs with secret redaction |
| Tests | pytest + pytest-asyncio | Unit, contract, integration, and UI tests |
| Property tests | Hypothesis (recommended) | Variable resolver and state invariants |
| Lint/format | Ruff | Consistent formatting and linting |
| Type checks | Pyright or mypy | Static analysis; choose one and enforce it |
| Packaging | Poetry | Dependency management, build, and `ambrosia` entry point |

### Implementation notes

- Start with SQLAlchemy's synchronous Session API and short database transactions. The UI and execution system can remain async. Move DB I/O to a worker thread if profiling shows UI blocking. Avoid adding async database complexity to the first milestone.
- Use `asyncio.create_subprocess_exec(program, *argv)` for process adapters. Do not use `shell=True` or `create_subprocess_shell` for manifest-driven commands.
- Use Textual workers for long-running tasks. Keep application state updates on the UI/event side through messages/events.
- Pydantic models are the validation boundary. Keep domain models independent of SQLAlchemy ORM models.
- YAML is data, not code. Never use `eval`, `exec`, pickle, or unsafe YAML object constructors to load presets.
- Do not use Jinja as an unrestricted expression language. Implement a small, typed reference syntax owned by Ambrosia.

---

## 6. Core architecture

```text
                 +---------------------------+
                 |       Interfaces          |
                 |    Textual TUI / Typer    |
                 +-------------+-------------+
                               |
                               v
                 +---------------------------+
                 |    Application Services   |
                 | engagement / action /     |
                 | preset / search / context |
                 +-------------+-------------+
                               |
             +-----------------+------------------+
             |                 |                  |
             v                 v                  v
      +-------------+   +-------------+    +-------------+
      | Context &   |   | Registry &  |    | Policy      |
      | Artifacts   |   | Resolver    |    | Engine      |
      +------+------+   +------+------+    +------+------+ 
             |                 |                  |
             +-----------------+------------------+
                               |
                               v
                 +---------------------------+
                 |     Workflow / Job Engine |
                 +-------------+-------------+
                               |
                               v
                 +---------------------------+
                 |     Executor Interfaces   |
                 | native / process /        |
                 | script / external plugin  |
                 +-------------+-------------+
                               |
                               v
                 +---------------------------+
                 | Parsers -> Artifacts ->    |
                 | Context Events -> UI      |
                 +---------------------------+
                               |
                               v
                 +---------------------------+
                 | SQLite / Evidence Files   |
                 +---------------------------+
```

The boxes describe logical components, not separate services. v0.x should be a modular monolith.

### 6.1 Package boundaries

- `domain`: Pydantic/domain types and enums. No UI, DB, or executor imports.
- `application`: use cases and service orchestration.
- `context`: context snapshots, artifact indexing, matching, and context events.
- `registry`: actions, packs, manifests, and validation.
- `presets`: preset schema, loader, validator, and variable resolver.
- `engine`: workflow planning, job scheduling, and execution coordination.
- `executors`: native and external-process execution adapters.
- `policy`: scope checking, effect classification, approvals, and audit decisions.
- `storage`: SQLAlchemy models, repositories, migrations, and evidence index.
- `tui`: Textual presentation only.
- `cli`: Typer commands that call application services.
- `packs`: built-in domain packs. Windows/AD is first.

### 6.2 Dependency direction

Allowed:

- interfaces -> application services
- application services -> domain and service protocols
- engines -> domain contracts, registry protocols, executor protocols, policy protocols
- storage implements repository protocols
- TUI and CLI call application services
- packs register definitions and handlers against stable contracts

Not allowed:

- domain -> Textual, Typer, SQLAlchemy, or concrete tools
- TUI -> direct subprocess execution
- CLI -> direct database queries
- preset parser -> arbitrary Python imports or execution
- action implementation -> direct UI mutations
- storage ORM objects escaping into the TUI

---

## 7. Core data flow

### 7.1 Artifact lifecycle

An artifact is immutable evidence or a typed observation. If information changes, create a new artifact or a superseding relationship rather than silently mutating historical evidence.

Minimum artifact fields:

- `id`: UUID/ULID string
- `engagement_id`
- `type`: namespaced type, e.g. `network.host`, `network.service`, `windows.domain`, `identity.user_ref`, `secret.ref`, `finding`, `evidence.ref`
- `value`: validated non-secret payload or safe display value
- `secret_ref`: optional pointer to a secret provider, never the secret itself
- `source`: action, preset, import, or operator
- `source_execution_id`
- `target_ref`: optional target/asset association
- `created_at`
- `confidence`: optional normalized value
- `sensitivity`: `public`, `internal`, `sensitive`, `secret`
- `scope_binding`: optional scope/target restrictions inherited from origin
- `expires_at`: optional TTL
- `metadata`: validated JSON object

### 7.2 Context

Context is an engagement-scoped, queryable view over operator inputs and artifacts. Do not store a second, divergent copy of every artifact as arbitrary context variables.

Context should expose well-defined namespaces:

- `engagement.*`
- `scope.*`
- `target.*`
- `context.selected_target.*`
- `artifacts.*`
- `facts.*` (only derived, typed facts with provenance)
- `last_execution.*`
- `user.*` (non-secret operator preferences only)

Derived facts must retain source artifact IDs and target provenance. An artifact discovered on host A must not silently become a fact about host B.

### 7.3 Action matching

The matcher evaluates each action against:

1. Pack enabled and action registered.
2. Platform compatibility.
3. Required artifact types and optional predicates.
4. Required local dependencies.
5. Target availability and scope validity.
6. Policy and approval state.
7. Required user inputs.

Return an `ActionAvailability` result with status, reasons, missing inputs, and matched artifact IDs. Matching must be side-effect-free.

### 7.4 Execution lifecycle

```text
DRAFT
  -> VALIDATED
  -> AWAITING_INPUT | AWAITING_APPROVAL
  -> READY
  -> RUNNING
  -> PARSING
  -> SUCCEEDED | PARTIAL | FAILED | CANCELLED | BLOCKED
```

Store every transition. Cancellation and timeouts must be explicit. Do not retry non-idempotent operations automatically. The initial built-in pack should avoid state-changing actions altogether.

---

## 8. Actions, presets, phases, and packs

### 8.1 Action contract

An action definition includes:

- stable namespaced ID, e.g. `network.nmap.service_discovery`
- version and compatibility declaration
- display name and detailed description
- category, tags, and optional user-defined phase memberships
- platform compatibility
- required artifacts and applicability conditions
- typed input schema
- declared outputs/artifact types
- executor kind and handler reference
- local dependencies/tool requirements
- effect classification and risk metadata
- scope fields to validate
- approval requirements
- parser references
- timeouts, output limits, and cancellation behavior
- documentation and examples

An action implementation must not access TUI state or storage internals. It receives a typed execution context and returns a typed result/event stream. User-created actions may wrap a fixed executable with an argv list or reference a script asset (Python, PowerShell, or another explicitly supported runtime). Script assets are separate files in a trusted local pack, not arbitrary code evaluated from YAML. They declare inputs, outputs, target fields, effects, interpreter, timeout, and approval requirements. The first version should support process-backed script files after the process executor is stable; a form-based inline code editor is postponed.

### 8.2 Preset contract

A preset is YAML/JSON data validated into Pydantic models. It can compose built-in actions, user-created command actions, and script-file actions. Users should be able to save their own command/script action as a reusable action definition and then include it in one or more presets. Presets themselves remain declarative; they do not contain unrestricted Python or shell code. A script action points to a separate, trusted script asset with a declared runtime and input contract. It contains:

- API version
- metadata (ID, name, version, description, author, tags)
- optional phase memberships
- declared variables and input schemas
- step list or small DAG
- step action IDs
- explicit input bindings
- `needs` dependencies
- supported `when` conditions
- output bindings
- optional approval checkpoints
- failure behavior
- preset-level effect summary

Initial workflow node types:

- `action`: execute a registered action
- `condition`: evaluate a constrained predicate
- `approval`: pause for explicit operator decision
- `output`: publish a named preset output

Do not add loops, arbitrary Python expressions, dynamic imports, or general-purpose scripting language features in v0.1. Add them only if a concrete use case and safety design justify them.

### 8.3 Variable resolution

Support typed references from:

- `inputs.*`: operator-provided preset inputs
- `context.*`: current engagement context
- `target.*`: selected or explicitly bound target
- `artifacts.*`: artifact references selected by stable ID or constrained query
- `steps.<step_id>.outputs.*`: output from earlier steps
- `preset.*`: preset metadata/defaults
- `secrets.*`: secret-provider references only

Rules:

1. Parse references using Ambrosia's grammar; do not execute them as Python.
2. Resolve values to typed objects before execution.
3. Missing required variables produce an input request, not an empty string.
4. Ambiguous artifact matches require operator selection.
5. Secret references remain opaque and are redacted in previews/logs.
6. A variable cannot override a scope boundary or policy setting.
7. Do not interpolate values into a shell command string.
8. For process actions, build an argv array and validate each argument against the action schema.
9. Support only explicit, reviewed transformations (e.g. validated host formatting); no arbitrary filters or function calls.

### 8.4 Phases

Phases are fully user-defined organizational metadata. They can group actions and presets, provide navigation labels, and define optional context predicates for surfacing a phase. A phase is not required for an action to execute and does not imply lifecycle order.

A user may create phases such as `before-auth`, `after-auth`, `domain-inventory`, `cleanup`, `incident-triage`, or `database-maintenance`. The core must not hard-code a canonical set.

### 8.5 Packs

A pack contains manifests and supporting assets. Initial built-in pack: `windows-assessment` with read-only discovery/configuration checks. Future packs may include Active Directory, web, Linux, cloud inventory, and general operations.

Pack loading must validate IDs, versions, schemas, references, dependencies, and duplicate conflicts before registration.

---

## 9. Preset example — safe read-only discovery

This is a target schema proposal. The builder team must implement and validate the schema before treating it as stable.

```yaml
api_version: ambrosia/v1
kind: preset

metadata:
  id: network.basic-discovery
  name: Basic Service Discovery
  version: 1.0.0
  description: Discover services on an explicitly scoped target.
  tags: [discovery, network, read-only]

phase_refs:
  - network.discovery

inputs:
  target:
    type: target.host
    required: true
    source: context_or_user
  ports:
    type: port_list
    required: true
    default: "80,443,445,3389"

steps:
  - id: discover
    action: network.nmap.service_discovery
    inputs:
      target: "{{ inputs.target }}"
      ports: "{{ inputs.ports }}"
    outputs:
      services: artifacts.network.services

  - id: suggest_smb_assessment
    type: condition
    when:
      artifact_type_exists:
        type: network.service
        where:
          service: smb
    then:
      - id: add_smb_suggestion
        type: output
        name: next_actions
        value:
          - windows.smb.configuration_audit
```

The condition/output syntax is illustrative and must be normalized into a documented Pydantic schema. It is intentionally not executable code.

---

## 10. Security and policy architecture

Security cannot be bolted on after the workflow engine exists. Policy validation must be called for every execution path, including CLI, TUI, presets, and plugins.

### 10.1 Scope model

Support:

- included IPs/CIDRs and hostnames/domains
- explicit exclusions
- optional permitted port/protocol restrictions
- engagement expiration
- maximum concurrency/rate limits
- action/effect restrictions
- approval requirements
- scope source/owner and notes

At runtime, resolve target references and validate every resolved address against scope. Handle DNS changes and redirects carefully. Never allow a preset variable to expand the target beyond the engagement scope.

### 10.2 Effect classes

Initial effect classes:

- `local_read`: read local metadata/configuration
- `local_write`: modify local files or settings
- `local_script`: run a user-authored local script in a separate process; requires explicit trust and review metadata
- `network_observe`: bounded, declared network discovery
- `remote_read`: read-only remote assessment
- `authentication`: perform an explicitly authorized authentication check
- `remote_change`: change target state
- `credential_access`: access sensitive credential material
- `unknown`: effect not sufficiently described

In v0.1 built-in modules should use `local_read` and explicitly scoped `network_observe`. More sensitive categories are represented in the policy model but unavailable in the initial built-in pack.

### 10.3 Required protections

- `shell=False` process execution; argument arrays only.
- Executable allowlisting or registered executable definitions for built-in process actions.
- No secrets in logs, command preview, YAML, DB values, crash reports, or evidence by default.
- Output size limits and execution timeouts.
- Cancellation that terminates managed child processes.
- Per-action scope validation and audit logging.
- Explicit approval for effects beyond read-only assessment.
- No automatic retries for non-idempotent actions.
- No deletion or alteration of target audit logs.
- Third-party plugins are not trusted merely because they are discovered.
- YAML safe loading; reject unknown fields unless forward compatibility is deliberately specified.
- No `eval`, `exec`, `pickle`, or arbitrary Python object deserialization for user-authored presets.

### 10.4 Secret handling

Define a `SecretStore` protocol early, but do not invent a home-grown cryptographic vault in the MVP. Support opaque secret references and an OS-backed provider when available. If there is no provider, do not persist secret values. Any action that requires a secret must declare it as a secret input and must not echo it into process output or telemetry.

Credential artifacts may record scheme/type metadata and a `secret_ref`, but the first release must not implement credential dumping, hash replay, password spraying, or automatic remote command execution. A later authentication-validation module requires a separate threat model and explicit authorization design.

---

## 11. Initial repository layout

```text
ambrosia/
├── pyproject.toml
├── poetry.lock
├── README.md
├── LICENSE
├── CHANGELOG.md
├── docs/
│   ├── architecture.md
│   ├── contracts.md
│   ├── presets.md
│   ├── plugin-development.md
│   ├── security-model.md
│   └── decisions/
├── src/
│   └── ambrosia/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli/
│       ├── tui/
│       ├── application/
│       ├── domain/
│       ├── context/
│       ├── artifacts/
│       ├── registry/
│       ├── actions/
│       ├── presets/
│       ├── phases/
│       ├── engine/
│       ├── executors/
│       ├── policy/
│       ├── storage/
│       ├── secrets/
│       └── packs/
│           └── windows_assessment/
├── builtin_presets/
├── schemas/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── tui/
│   └── fixtures/
└── examples/
    ├── presets/
    └── packs/
```

Keep source package under `src/`. Tests should not import from the repository root by accident; install the project in editable mode for development.

---

## 12. First vertical slice — definition of MVP

The first release is not dozens of Windows modules. It is one end-to-end system proving the architecture.

### v0.1 must do

1. Start with `ambrosia` and show an adaptive Textual workspace.
2. Create/open an engagement.
3. Define and validate scope.
4. Add a target.
5. Load built-in action definitions.
6. Search and inspect actions.
7. Run a bounded, read-only service-discovery action against an in-scope lab target.
8. Parse structured output into typed service artifacts.
9. Persist artifacts and execution records to SQLite.
10. Recompute context and show new applicable actions.
11. Validate a YAML preset.
12. Execute the same discovery through a preset in dry-run and normal approved mode.
13. Export JSON evidence/report.
14. Run all tests without requiring a live network target.

### v0.1 deliberately does not include

- A visual or inline code editor. User-authored command/script actions can be added as reviewed local files with manifests in a custom pack; the editor can come later.
- Credential extraction or credential replay.
- Lateral movement or remote command execution.
- Persistence, stealth/evasion, or exfiltration features.
- A general-purpose remote agent.
- Arbitrary Python loaded into the main process from user folders.
- A complex workflow DSL with loops or user code expressions.
- A web dashboard or distributed server.
- Mandatory fixed pentesting phases.

### v0.1 demo scenario

- Create engagement `lab-windows`.
- Add scope `192.0.2.10/32` (documentation-only example address) and a target.
- Run `network.nmap.service_discovery` with a small explicit port list.
- Use fixture XML in automated tests; use a live target only in a lab explicitly added to scope.
- Parse SMB/RDP/HTTP service records if present.
- Context matcher surfaces registered SMB/RDP/HTTP configuration audit actions.
- User opens one suggestion and sees its requirements/options.
- User saves the discovery sequence as a preset.
- Export an engagement artifact bundle.

---

## 13. CLI surface

CLI commands must call application services, never reach directly into repositories or execute tools themselves.

Proposed initial commands:

```text
ambrosia
ambrosia version
ambrosia engagement create <name>
ambrosia engagement list
ambrosia engagement use <id>
ambrosia scope show
ambrosia scope add <target>
ambrosia target add <host>
ambrosia target list
ambrosia actions list
ambrosia actions info <action-id>
ambrosia actions check <action-id>
ambrosia preset list
ambrosia preset validate <path>
ambrosia preset plan <preset-id> --dry-run
ambrosia preset run <preset-id>
ambrosia jobs list
ambrosia jobs show <job-id>
ambrosia report export --format json
```

Exact names can be adjusted during implementation, but preserve consistent command groups and a script-friendly JSON output option.

---

## 14. Delivery stages

| Stage | Deliverable | Gate |
|---|---|---|
| 0 | Repository skeleton, ADRs, shared contracts, test conventions | All agents agree on contract IDs and types |
| 1 | Domain models, context/artifacts, storage, registry, policy protocols | Unit/contract tests pass independently |
| 2 | Preset schema, resolver, workflow planner, safe executor | Dry-run produces deterministic plans |
| 3 | CLI and adaptive Textual shell | Both interfaces call the same services |
| 4 | First discovery adapter and parser | Fixture-based integration test passes |
| 5 | Context-driven suggestions and persistence | Vertical slice demo passes |
| 6 | Windows read-only pack, docs, packaging | Release checklist passes |

Do not start Stage 4 domain modules before the shared action, artifact, execution, and policy contracts are stable.

---

## 15. Definition of done

A feature is done only when:

- Its behavior is documented.
- Its public contracts are typed and validated.
- Unit tests cover success, invalid input, and failure behavior.
- It has no direct TUI dependency unless it is UI code.
- It does not leak secrets into logs or persisted outputs.
- Policy and scope checks are applied on every execution path.
- It supports cancellation/timeouts where it starts work.
- It produces stable, structured errors.
- It has a CLI or TUI integration test where relevant.
- Ruff and the selected static type checker pass.
- Tests pass on supported operating systems or platform limitations are documented.

---

## 16. Technical references

- Textual: https://textual.textualize.io/
- Textual workers: https://textual.textualize.io/guide/workers/
- Textual screens: https://textual.textualize.io/guide/screens/
- Typer: https://typer.tiangolo.com/
- Pydantic validation: https://pydantic.dev/docs/validation/latest/
- Pydantic Settings: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- Python packaging plugin discovery: https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/
- Python entry-points specification: https://packaging.python.org/en/latest/specifications/entry-points/
- Python asyncio subprocesses: https://docs.python.org/3/library/asyncio-subprocess.html
- SQLAlchemy ORM: https://docs.sqlalchemy.org/en/20/orm/
- Alembic: https://alembic.sqlalchemy.org/
- Pluggy: https://pluggy.readthedocs.io/

These references inform implementation choices; they do not replace Ambrosia's own contracts and security requirements.
