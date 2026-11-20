# ADR 0003 — Typed, immutable artifacts with provenance

- Status: Accepted
- Date: 2026-11-20

## Context

Tool output passed between actions as untyped strings loses meaning, origin,
and target binding, making reproducibility and cross-target safety impossible.

## Decision

Outputs become typed artifacts with `type`, validated `value`, `source`,
`source_execution_id`, `target_ref`, `sensitivity`, `secret_ref`, and optional
expiry/scope binding. Artifacts are immutable; changes are represented by
superseding relationships. Derived facts retain source artifact ids.

## Consequences

- Availability matching can explain *which* artifact made an action relevant.
- Cross-target reuse is blocked by default (`same_target=True` requirements).
- Secret material cannot be represented in artifact values; only opaque refs.
- Some extra storage and validation work per produced artifact.
