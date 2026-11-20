# ADR 0004 — Actions are the smallest unit; presets compose them

- Status: Accepted
- Date: 2026-11-20

## Context

Reusable automation needs a stable unit of execution that can be tested and
composed in different sequences.

## Decision

An `ActionDefinition` plus an `ActionHandler` performs one well-described
operation. A preset composes actions (and condition/approval/output steps) into
repeatable workflows. Action ids are namespaced and versioned; they are never
reused for a different operation.

## Consequences

- Actions are independently testable with fake executors and fixtures.
- Presets stay declarative and small.
- Each action must declare inputs, effects, dependencies, scope fields, and
  timeouts up front, increasing definition verbosity but improving safety.
