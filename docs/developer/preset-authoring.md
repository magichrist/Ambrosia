# Preset authoring

Presets are `ambrosia/v1` YAML data validated into Pydantic models. Start from
`builtin_presets/network.basic-discovery.yaml` or
`src/ambrosia/packs/windows_assessment/examples/basic_discovery_preset.yaml`.

## Minimum document

```yaml
api_version: ambrosia/v1
kind: preset
metadata:
  id: team.my-workflow
  name: My Workflow
  version: 1.0.0
  description: What this workflow does.
inputs:
  target:
    type: target.host
    required: true
    source: context_or_user
steps:
  - id: discover
    type: action
    action: network.nmap.service_discovery
    inputs:
      target: "{{ inputs.target }}"
      ports: "80,443,445"
```

## Rules

- Use stable, namespaced, versioned ids; never reuse an id for a different workflow.
- Step ids must be unique. `needs`, output references, and branch targets must
  refer to known steps; cycles are rejected.
- Supported step types: `action`, `condition`, `approval`, `output`.
- Condition predicates: `artifact_exists`, `artifact_field_equals`,
  `input_present`. Branches use `then: [step-id]` / `else: [step-id]`.
- References are exact tokens only: `{{ inputs.* }}`, `{{ context.* }}`,
  `{{ target.* }}`, `{{ artifacts.* }}`, `{{ steps.*.outputs.* }}`,
  `{{ secrets.* }}`, `{{ preset.* }}`. No expressions, filters, or interpolation.
- Unknown fields are rejected. Python object tags are rejected by safe loading.

## Validation loop

```bash
ambrosia preset validate my-workflow.yaml
ambrosia preset plan team.my-workflow
ambrosia preset save my-workflow.yaml --as team.my-workflow-copy
```

Put your YAML in a directory passed as `presets_dirs`, or save it into the
workspace presets directory (`.ambrosia/presets`) so `list`/`plan`/`run` can find
it. `preset save` is the supported way to fork a workflow under a new id without
overwriting an existing one.

## Testing a preset

Add a fixture YAML and assert: it validates, its dry-run plan is deterministic,
it starts no process, missing inputs surface as structured requests, and
invalid variants (duplicate steps, cycles, unknown action, bad reference) are
rejected. See `tests/unit/test_preset_loader.py` and
`tests/unit/application/test_preset_service.py`.
