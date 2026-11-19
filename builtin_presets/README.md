# Built-in presets

This directory contains example :term:`preset` documents (``ambrosia/v1``).
Presets are declarative YAML/JSON action workflows. They are validated into
Pydantic domain models (the authoritative schema) and executed by the preset
engine; they never contain executable code.

## Document shape

```yaml
api_version: ambrosia/v1   # must be exactly "ambrosia/v1"
kind: preset               # must be exactly "preset"
metadata:
  id: <namespaced id>      # e.g. network.basic-discovery
  name: <display name>
  version: <semver>
  description: <text>
  author: <optional>
  tags: [<list>]
phase_refs: [<phase ids>]  # organizational only; see docs/01_SHARED_CONTRACTS.md 7
inputs:
  <input-id>:
    type: <type hint>          # e.g. target.host, string, integer
    required: <bool>           # default false
    default: <literal value>   # optional
    source: context_or_user    # context_or_user | user | context
steps:
  - id: <step id>
    type: action | condition | approval | output   # default action
    action: <registered action id>                 # required for action steps
    needs: [<step id>, ...]                        # ordered dependencies
    when: <constrained predicate>                  # see below
    inputs:
      <name>: <literal> | "{{ <reference> }}"
    outputs:
      <name>: { source: "{{ <reference> }}" }
    on_failure: stop | continue                    # default stop
  # condition steps may declare branches:
  # then: [<step id>, ...]
  # else: [<step id>, ...]
outputs:
  <name>: { source: "<reference>" }
```

## Variable references

A complete binding token must be ``{{ <namespace>.<path> }}``. Free-form
interpolation (``prefix {{ x }}``), transformation functions, imports, loops,
and arbitrary expressions are rejected. Supported namespaces
(``docs/01_SHARED_CONTRACTS.md`` section 6):

* ``inputs.<name>`` — operator-provided preset input
* ``context.<path>`` — engagement context snapshot
* ``target.<path>`` — selected target
* ``artifacts.<id>[.<field path>]`` — artifact by stable id
* ``steps.<step-id>.outputs.<name>`` — earlier step output
* ``preset.<path>`` — preset metadata
* ``secrets.<name>`` — opaque secret handle only; plaintext is never
  available to the preset engine, previews, or logs

## Constrained predicates (``when``)

Only these predicate kinds are supported (no arbitrary expressions):

* ``artifact_exists``: at least one artifact of a type exists, optionally
  filtered by a literal ``where`` mapping
* ``artifact_field_equals``: an artifact of a type has a field equal to an
  enumerated literal
* ``input_present``: a preset input has been provided

## Safety

* YAML is loaded with ``yaml.safe_load`` only. Python object tags
  (``!!python/object`` and friends) are rejected before validation.
* Unknown document fields are rejected (Pydantic ``extra="forbid"``).
* ``secrets.*`` resolves to an opaque :class:`SecretHandle`; the preset layer
  never sees secret plaintext.
* A dry-run resolves bindings and produces a plan without invoking any action
  handler or executor.

## Authoring

The JSON-schema rendering of the Pydantic model lives in
``schemas/preset.schema.json``; Pydantic remains the authoritative validator.
See ``docs/01_SHARED_CONTRACTS.md`` sections 5-6 for the frozen contracts.
