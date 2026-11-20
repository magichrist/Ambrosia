# Presets

A preset is a reusable, declarative `ambrosia/v1` document. It is validated
data, never executable code. The authoritative parser is the Pydantic model
`ambrosia.domain.preset.PresetDefinition`; the JSON Schemas in `schemas/` are
generated companions.

## Document shape

```yaml
api_version: ambrosia/v1
kind: preset
metadata:
  id: network.basic-discovery      # lowercase, dot-separated namespaces
  name: Basic Service Discovery
  version: 1.0.0
  description: Discover services on an explicitly scoped target.
  tags: [discovery, network, read-only]
phase_refs: [network.discovery]     # navigation labels only
inputs:
  target:
    type: target.host
    required: true
    source: context_or_user
  ports:
    type: string
    required: false
    default: "80,443,445,3389"
steps:
  - id: discover
    type: action
    action: network.nmap.service_discovery
    inputs:
      target: "{{ inputs.target }}"
      ports: "{{ inputs.ports }}"
    outputs:
      services: { source: "{{ steps.discover.outputs.services }}" }
    on_failure: stop
  - id: suggest_smb
    type: condition
    when:
      kind: artifact_field_equals
      artifact_type: network.service
      field: service_name
      value: microsoft-ds
    then: [publish_smb]
  - id: publish_smb
    type: output
    outputs:
      next_actions: { source: "{{ steps.suggest_smb.outputs.result }}" }
outputs:
  services: { source: "{{ steps.discover.outputs.services }}" }
```

## Step types

- `action` — runs a registered action with typed input bindings.
- `condition` — evaluates a constrained predicate and gates its `then`/`else` branches.
- `approval` — explicit operator checkpoint.
- `output` — publishes a named output from context, artifacts, or an earlier step.

`then` and `else` are engine-level branch keys. They are stripped before strict
domain validation by `ambrosia.presets.normalize.normalize_engine_step_keys`,
shared by the loader and the application service, then restored into the
execution plan. Unknown keys are still rejected.

## Predicates

Supported `when` kinds: `artifact_exists`, `artifact_field_equals`,
`input_present`. Predicates are a fixed grammar — no expressions or Python.
Branch steps are wired to their condition as dependencies automatically.

## Variable references

Exact-reference syntax only:

```
{{ inputs.target }}
{{ context.selected_target.address }}
{{ artifacts.<artifact-id>.value.hostname }}
{{ steps.<step-id>.outputs.<name> }}
{{ secrets.<name> }}
{{ target.address }}
{{ preset.metadata.id }}
```

A command argument is either a literal or one complete typed reference; there
is no string interpolation. Lists/objects are passed as structured values, not
`str()`. Missing required inputs become structured input requests; ambiguous
artifact matches require operator selection. Secret references resolve to
opaque handles and are redacted in previews and logs. There are no
transformation functions in v0.1.

## Commands

```bash
ambrosia preset list
ambrosia preset validate path/to/preset.yaml
ambrosia preset plan <preset-id>
ambrosia preset run <preset-id> --engagement <id>
ambrosia preset save path/to/preset.yaml --as network.my-copy --name "My Copy"
```

`validate` reports structured errors/warnings (including duplicate step ids,
cycles, unknown actions, invalid references). `plan` is deterministic and never
launches a process. `run` re-validates, policy-checks every action step, then
delegates to the job engine. `save` forks a validated preset into the writable
workspace directory (`.ambrosia/presets` by default) under a fresh namespaced
id; existing ids are never silently overwritten. Saved presets appear in
`preset list` immediately.

From the TUI, open `p` (preset browser) and use **Save a copy...** to fork the
selected preset.

## Safety

`yaml.safe_load` only; Python object tags, unknown fields, duplicate/cyclic step
graphs, unknown branch targets, and invalid references are rejected. Dry-run
starts no process. Preset variables cannot override scope or policy settings.
