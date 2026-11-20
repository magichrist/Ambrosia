# ADR 0009 — Synchronous SQLAlchemy repositories at first

- Status: Accepted
- Date: 2026-11-20

## Context

SQLite with short transactions is sufficient for v0.1. Adding async database
complexity would slow delivery without measured benefit.

## Decision

Use SQLAlchemy 2.x synchronous `Session` with short transactions in repository
classes. The UI and execution engine remain async. Repository APIs return
domain objects, never ORM instances.

## Consequences

- Tests use an in-memory SQLite database with no async DB fixtures.
- A `datetime` import in `storage/models.py` must stay at runtime with a
  `noqa: TC003` because SQLAlchemy resolves `Mapped[datetime]` at mapper time.
- Blocking DB work can be moved to worker threads if profiling shows UI impact.
