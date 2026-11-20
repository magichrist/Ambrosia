# ADR 0006 — Trusted in-process built-ins; process-isolated future plugins

- Status: Accepted
- Date: 2026-11-20

## Context

The product needs extensibility, but loading arbitrary third-party Python into
the main process is not isolation. Python entry points identify installed code;
they do not make it safe.

## Decision

Built-in actions are trusted Python registered by packs inside the main
process. Future third-party extensions (M7) communicate over a versioned
JSON-RPC 2.0 stdio protocol from separate processes, with capability
declarations, compatibility checks, and schema-validated outputs. Plugin
discovery never implies trust, and plugin requests pass through policy.

## Consequences

- No plugin sandbox exists in v0.1; external functionality must be reviewed
  and shipped as a built-in pack.
- The executor layer is kept behind protocols so the plugin boundary can be
  added without rewriting the core.
- M7 remains an explicit, postponed roadmap item.
