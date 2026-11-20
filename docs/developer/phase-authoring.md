# Phase authoring

Phases are user-defined organizational labels. They group actions and presets
for navigation and may control when a phase is *surfaced*. They never grant
permission, mutate context, or impose a lifecycle order.

## Document shape

```yaml
api_version: ambrosia/v1
kind: phase
id: windows.discovery
name: Windows Discovery
description: Read-only discovery and inventory.
tags: [windows, discovery]
action_refs:
  - network.nmap.service_discovery
  - windows.smb.configuration_audit
preset_refs:
  - windows.basic-discovery
visible_when:
  - kind: artifact_exists
    artifact_type: network.service
sort_order: 100
```

## Schema

`PhaseDefinition` (in `domain/phase.py`) uses `extra="forbid"` and requires `id`
and `name`. Optional fields: `description`, `tags`, `action_refs`,
`preset_refs`, `visible_when`, `sort_order`. Predicates are the same constrained
kinds used by presets (`artifact_exists`, `artifact_field_equals`,
`input_present`). `visible_when` entries are ANDed.

## Loading

`ambrosia.phases.catalog.PhaseCatalog` loads `.yaml`, `.yml`, and `.json` files.
It provides deterministic listing (by `sort_order`, then id), lookup, unknown
reference detection, and pure visibility evaluation.

## Invariants to preserve

- Removing all phases must not change which actions can execute.
- An action belonging to a non-selected phase remains discoverable via global
  search.
- Changing phase selection must not mutate context or grant access.

Tests in `tests/unit/test_phases.py` cover these invariants.
