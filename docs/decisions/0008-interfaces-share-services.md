# ADR 0008 — Textual and Typer share application services

- Status: Accepted
- Date: 2026-11-20

## Context

Duplicating use cases in the CLI and TUI would cause divergent behavior,
especially for policy and scope enforcement.

## Decision

All business behavior lives in `ambrosia.application` services that return
typed DTOs. Typer commands are thin wrappers; Textual views call a
`TUIServiceAdapter` over the same services. Neither interface queries
SQLAlchemy or launches subprocesses directly.

## Consequences

- CLI and TUI are contract-tested for parity.
- A blocked action or policy decision behaves identically in both interfaces.
- Adding an interface (future API) requires only presentation work.
