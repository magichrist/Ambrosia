# ADR 0005 — Declarative presets and strict typed references

- Status: Accepted
- Date: 2026-11-20

## Context

Allowing general-purpose expressions in preset YAML would permit code
execution hidden in data and would make data-flow validation impossible.

## Decision

Presets are Pydantic-validated data loaded with `yaml.safe_load`. References use
a small Ambrosia-owned exact-token grammar (`{{ inputs.x }}`, etc.), with no
`eval`, `exec`, pickle, arbitrary Jinja, loops, dynamic imports, or
transformation functions in v0.1. A missing or ambiguous reference becomes a
structured request, not an empty string. Secrets resolve to opaque handles.

## Consequences

- Presets are diffable, reviewable, and deterministic to dry-run.
- Authors cannot express arbitrary computation in a preset; new transformations
  require a reviewed grammar extension.
- Branch keys (`then`/`else`) are engine metadata stripped before strict schema
  validation by a shared normalization helper.
