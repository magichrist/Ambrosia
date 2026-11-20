# Action authoring

An action is immutable metadata (`ActionDefinition`) plus a trusted Python
handler (`ActionHandler`). Keep them separate.

## 1. Declare the definition

```python
from ambrosia.domain.action import (
    ActionDefinition, ArtifactRequirement, ExecutorReference, ToolDependency,
)

definition = ActionDefinition(
    id="network.nmap.service_discovery",       # lowercase, dotted, versioned
    version="1.0.0",
    name="Nmap Service Discovery",
    description="Bounded read-only service discovery on a scoped target.",
    category="discovery",
    tags=["network", "read-only"],
    platforms=["linux", "windows", "darwin"],
    phase_refs=["windows.discovery"],          # navigation only
    required_artifacts=[],                     # or ArtifactRequirement(...)
    input_schema={
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "ports": {"type": "string"},
        },
        "required": ["target", "ports"],
        "additionalProperties": False,
    },
    output_artifact_types=["network.service"],
    executor=ExecutorReference(kind="process", executable="nmap"),
    dependencies=[ToolDependency(name="nmap", check_command=["nmap", "--version"])],
    effects=["network_observe"],
    risk="low",
    scope_fields=["target"],
    approval_required=False,
    timeout_seconds=60,
    max_output_bytes=2_000_000,
    parser_refs=[],
)
```

Rules: ids are lowercase dot-separated segments (at least two); versions are
semantic; effect classes come from the security model; tool checks are metadata
only. `scope_fields` must name the input fields that carry target addresses so
the engine can re-validate them at execution time.

## 2. Implement the handler

`ActionHandler.execute(request, context)` is a synchronous method returning an
`AsyncIterator[ExecutionEvent]` (implement it as an `async generator`):

```python
class MyHandler:
    async def execute(self, request, context):
        yield ProgressEvent(execution_id=request.execution_id, payload={"message": "start"})
        ...
        yield ArtifactProducedEvent(execution_id=request.execution_id, payload=draft)
        yield CompletedEvent(execution_id=request.execution_id, payload={"summary": {...}})
```

Emit progress, output chunks, artifact/finding drafts, and a terminal completed
or failed event. Never touch TUI widgets, storage internals, or arbitrary
executables. Use the context's redacting logger and resolver only.

## 3. Register

Register through a pack's `register_pack()` (see `pack-authoring.md`) so the
manifest is validated and the handler is associated with the definition.
Registration must not execute any tool.

## 4. Test

- metadata validation (id/version/effects/dependencies)
- availability for each status (including target-bound artifact requirements)
- a fake executor produces the expected events and artifacts
- out-of-scope targets are refused on the engine path
- dry-run starts no process

See `tests/unit/packs/` and `tests/contract/packs/` for examples.
