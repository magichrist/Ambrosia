# ADR 0007 — Shell-free argv execution and runtime scope checks

- Status: Accepted
- Date: 2026-11-20

## Context

Command injection and scope bypass are the highest-risk failure modes for a
tool-driving workbench.

## Decision

Process actions use `asyncio.create_subprocess_exec` with argv arrays and no
shell. The executable comes from the action's registered allowlist, never from
untrusted input. Every target is re-validated against scope immediately before
execution, on every path. Output is capped, timeouts and cancellation terminate
and reap children, and no non-idempotent action is auto-retried.

## Consequences

- Shell metacharacters are passed as data, not interpreted.
- A preset variable cannot expand a target outside scope.
- All process tests use harmless local fixtures or fake executors.
