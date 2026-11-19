# Ambrosia — Shared Contracts and Interface Specification

This document is the integration boundary for all builder agents. The lead agent should review and freeze these contracts before parallel implementation begins.

## 1. Naming and IDs

- Python distribution: `ambrosia`
- Import package: `ambrosia`
- CLI executable: `ambrosia`
- Preset API version: `ambrosia/v1`
- IDs: lowercase namespaced strings using dot-separated segments.
- Examples: `network.nmap.service_discovery`, `windows.smb.configuration_audit`, `network.basic_discovery`.
- Do not reuse an ID for a different semantic operation.
- Every extensible definition has a version.

## 2. Common result and error contracts

All application services should return typed values or raise typed domain/application errors. Avoid returning arbitrary dictionaries from core interfaces.

Suggested error hierarchy:

```python
class AmbrosiaError(Exception): ...
class ValidationError(AmbrosiaError): ...
class NotFoundError(AmbrosiaError): ...
class ConflictError(AmbrosiaError): ...
class ScopeViolationError(AmbrosiaError): ...
class PolicyBlockedError(AmbrosiaError): ...
class MissingInputError(AmbrosiaError): ...
class MissingDependencyError(AmbrosiaError): ...
class ExecutionError(AmbrosiaError): ...
class ExecutionTimeoutError(ExecutionError): ...
class ExecutionCancelledError(ExecutionError): ...
class ParseError(AmbrosiaError): ...
```

A public error should include a stable `code`, a safe human-readable message, and structured non-secret details. Never include secret values in exception messages.

## 3. Domain contracts

The initial models should be Pydantic v2 models or dataclasses with explicit validation. Domain models must not import SQLAlchemy, Textual, or Typer.

### 3.1 Engagement

```python
class Engagement(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: Literal["active", "paused", "archived"] = "active"
    created_at: datetime
    updated_at: datetime
    scope_id: str | None = None
```

### 3.2 Scope

```python
class Scope(BaseModel):
    id: str
    engagement_id: str
    include_hosts: list[str] = []
    include_cidrs: list[str] = []
    include_domains: list[str] = []
    exclude_hosts: list[str] = []
    exclude_cidrs: list[str] = []
    allowed_ports: list[int] | None = None
    expires_at: datetime | None = None
    max_concurrency: int = 2
    max_requests_per_second: float | None = None
    allowed_effects: set[str] = {"local_read", "network_observe"}
    require_approval_for: set[str] = {"local_write", "remote_change", "authentication"}
```

The real implementation must validate IP/CIDR/domain values and prevent include/exclude ambiguity. Defaults must be conservative. An empty scope does not mean allow all.

### 3.3 Artifact

```python
class Artifact(BaseModel):
    id: str
    engagement_id: str
    type: str
    value: dict[str, object]
    source_kind: Literal["action", "preset", "operator", "import"]
    source_id: str | None = None
    source_execution_id: str | None = None
    target_ref: str | None = None
    created_at: datetime
    confidence: float | None = None
    sensitivity: Literal["public", "internal", "sensitive", "secret"] = "internal"
    secret_ref: str | None = None
    scope_binding: dict[str, object] | None = None
    supersedes: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, object] = {}
```

`value` must not contain raw secret material. For sensitive data use `secret_ref` and safe metadata. Implement artifact-type-specific Pydantic schemas for built-in artifacts; do not rely only on arbitrary dicts.

### 3.4 Execution

```python
ExecutionStatus = Literal[
    "draft", "validated", "awaiting_input", "awaiting_approval",
    "ready", "running", "parsing", "succeeded", "partial",
    "failed", "cancelled", "blocked",
]

class ExecutionRecord(BaseModel):
    id: str
    engagement_id: str
    action_id: str | None = None
    preset_id: str | None = None
    status: ExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    target_refs: list[str] = []
    input_summary: dict[str, object] = {}
    output_artifact_ids: list[str] = []
    error_code: str | None = None
    error_message: str | None = None
    initiated_by: str = "operator"
```

`input_summary` must redact secret values and avoid recording raw credentials.

## 4. Action contract

Separate immutable action metadata from the Python handler implementation.

```python
class ActionDefinition(BaseModel):
    id: str
    version: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    platforms: list[str] = []
    phase_refs: list[str] = []
    required_artifacts: list[ArtifactRequirement] = []
    input_schema: dict[str, object]
    output_artifact_types: list[str] = []
    executor: ExecutorReference
    dependencies: list[ToolDependency] = []
    effects: list[str]
    risk: Literal["info", "low", "moderate", "high", "critical"]
    scope_fields: list[str] = []
    approval_required: bool = False
    timeout_seconds: int = 60
    max_output_bytes: int = 2_000_000
    parser_refs: list[str] = []
```

`required_artifacts` and `input_schema` must be validated. Use JSON Schema generated from Pydantic models where possible, but retain the authoritative Pydantic input model in code for built-ins.

### 4.1 Action handler protocol

```python
class ActionHandler(Protocol):
    async def execute(
        self,
        request: ActionRequest,
        context: ActionExecutionContext,
    ) -> AsyncIterator[ExecutionEvent]: ...
```

`ActionRequest` contains validated, resolved inputs and an execution ID. `ActionExecutionContext` exposes read-only services: current engagement/scope snapshot, event emitter, logger with redaction, secret resolver, and cancellation token. It must not expose the TUI application instance or raw SQLAlchemy session.

`ExecutionEvent` variants:

- `ProgressEvent(message, percent=None)`
- `LogEvent(level, message, fields={})`
- `OutputChunkEvent(stream, text)`
- `ArtifactProducedEvent(artifact_draft)`
- `FindingProducedEvent(finding_draft)`
- `ApprovalRequestedEvent(reason, required_effect)`
- `CompletedEvent(summary)`
- `FailedEvent(code, message, retryable=False)`

Events must be serializable where they cross process boundaries.

### 4.2 Availability contract

```python
class ActionAvailability(BaseModel):
    action_id: str
    status: Literal[
        "available", "needs_input", "needs_approval", "blocked",
        "missing_dependency", "not_applicable",
    ]
    reasons: list[str] = []
    missing_inputs: list[str] = []
    matched_artifact_ids: list[str] = []
    required_approval: bool = False
```

The matcher is pure: same registry + context + policy snapshot -> same availability result.

## 5. Preset contract

Use Pydantic models as the authoritative parser/validator. The YAML document is only a serialized representation.

```python
class PresetDefinition(BaseModel):
    api_version: Literal["ambrosia/v1"]
    kind: Literal["preset"] = "preset"
    metadata: PresetMetadata
    phase_refs: list[str] = []
    inputs: dict[str, PresetInput]
    steps: list[PresetStep]
    outputs: dict[str, OutputBinding] = {}
```

### 5.1 Step model

Initial step types:

- `action`: references a registered action and binds typed inputs.
- `condition`: evaluates an allowed predicate and chooses among declared branches.
- `approval`: creates an approval checkpoint.
- `output`: publishes a named output from existing context/artifacts/step output.

A step has a stable `id`, optional `needs` dependencies, `when` conditions, and input/output bindings.

Do not allow arbitrary Python expressions, `eval`, imports, or unrestricted Jinja in predicates or bindings.

## 6. Variable reference grammar

Use exact references such as:

```text
{{ inputs.target }}
{{ context.selected_target.address }}
{{ artifacts.<artifact-id>.value.hostname }}
{{ steps.discovery.outputs.services }}
{{ secrets.<secret-name> }}
```

Initial implementation requirements:

- Reference parser must be a small grammar with unit tests.
- Only a complete argv/input binding token may be substituted in v0.1; no free-form expression interpolation.
- A command argument may be a literal argument or one complete typed reference. The resolver emits an argv array; it never constructs a shell command string.
- For structured values, the destination input must accept that structured type.
- Lists/objects must be serialized explicitly by a destination-specific adapter, never by Python `str()`.
- A missing or ambiguous reference must stop planning and return a typed prompt/selection request.
- `secrets.*` resolves to an opaque secret handle, not plaintext.
- No transformation functions in v0.1.

## 7. Phase contract

```python
class PhaseDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    tags: list[str] = []
    action_refs: list[str] = []
    preset_refs: list[str] = []
    visible_when: list[Predicate] = []
    sort_order: int = 100
```

The phase is a navigation/grouping object only. It cannot mandate the next phase, mutate context, or grant permission.

## 8. Context event contract

Use explicit events to drive UI reactivity and persist history:

- `EngagementSelected`
- `ScopeChanged`
- `TargetAdded`
- `ArtifactCreated`
- `ArtifactSuperseded`
- `ExecutionStateChanged`
- `ActionAvailabilityChanged`
- `PhaseConfigurationChanged`
- `PresetSaved`
- `PolicyDecisionRecorded`

Events contain IDs and safe summaries, not secret values. Event handlers must be idempotent where possible.

## 9. Repository protocols

The application layer should depend on protocols such as:

```python
class EngagementRepository(Protocol):
    def get(self, engagement_id: str) -> Engagement | None: ...
    def create(self, engagement: Engagement) -> Engagement: ...
    def list(self) -> list[Engagement]: ...

class ArtifactRepository(Protocol):
    def add(self, artifact: Artifact) -> Artifact: ...
    def list_for_engagement(self, engagement_id: str) -> list[Artifact]: ...
    def get(self, artifact_id: str) -> Artifact | None: ...

class ExecutionRepository(Protocol):
    def add(self, execution: ExecutionRecord) -> ExecutionRecord: ...
    def update(self, execution: ExecutionRecord) -> None: ...
    def list_for_engagement(self, engagement_id: str) -> list[ExecutionRecord]: ...
```

Repositories return domain objects, never ORM model instances.

## 10. Process executor contract

A process action definition must specify:

- fixed executable name or registered executable ID
- argv as a list of distinct arguments
- optional script asset reference and fixed interpreter ID (for Python/PowerShell or another explicitly supported runtime); script content must be a separate trusted file, not evaluated from YAML
- typed variable references in individual argument positions
- working directory policy
- environment allowlist
- timeout
- output byte cap
- expected output format/parser
- declared target fields for scope validation
- declared effects

Implementation rules:

- use `asyncio.create_subprocess_exec` (no shell)
- never run arbitrary interpolated shell strings
- do not log environment secrets
- stream stdout/stderr with size limits
- terminate the child on timeout/cancellation and reap it
- capture exit code and duration
- parse machine-readable output when available

## 11. Storage contract

Use SQLAlchemy ORM models privately in `storage`. Map the following concepts:

- engagement
- scope
- target
- artifact
- execution
- execution_event
- finding
- preset_execution (optional if execution table can represent it)
- approval_record
- secret_reference metadata (not secret values)

Filesystem evidence should be stored under an application data directory with generated IDs, not user-provided paths. Store a content hash, media type, size, source execution, creation time, and safe path reference in SQLite.

## 12. Cross-agent integration rules

- Do not rename a shared model or field without notifying the lead and updating this document.
- No agent should import another agent's implementation-private module. Import only public interfaces/contracts.
- Do not change `pyproject.toml` or dependency versions except the integration owner.
- Do not add new core abstractions without documenting the use case and asking the lead.
- All public interfaces require type annotations and tests.
- Do not commit generated database files, local config, engagement data, or secret material.
