# ADR 0001 — Modular monolith for v0.x

- Status: Accepted
- Date: 2026-11-20

## Context

The product needs strong separation between domain logic, orchestration,
persistence, and two interfaces. A distributed design would add deployment and
consistency complexity before the vertical slice is proven.

## Decision

Build one Python application (`ambrosia`) with strongly separated packages
enforced by import conventions and contract tests. Logical components are not
separate services.

## Consequences

- Local installation, testing, and debugging stay simple.
- A future plugin boundary (ADR 0006) is added at the executor edge, not by
  splitting the core.
- Discipline is required: forbidden import directions are checked by review
  and contract tests rather than by process isolation.
