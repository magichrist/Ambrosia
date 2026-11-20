# ADR 0012 — Opt-in authorized operations pack

- Status: Accepted
- Date: 2026-11-20
- Supersedes: the read-only-only default in ADR 0010 *for explicitly authorized engagements only*

## Context

Operators need to wrap installed Windows/AD red-team binaries (Impacket,
NetExec, samdump2) so tool invocations are policy-checked, attributable, and
reproducible. The original plan excluded credential access, remote execution,
and lateral movement from built-in actions. The operator requested these
capabilities with an explicit instruction that the tools are not installed in
the development environment and must not be installed — only supported.

## Decision

Add a **separate, opt-in** pack (`authorized_operations`) that wraps installed
binaries through the existing shell-free argv executor. It is never registered
by default startup. Every high-impact action is governed by four independent
gates: explicit pack registration, scope effect allowlisting, a per-run
authorization reference, and the engine's approval state. Raw tool output is
not persisted unless the operator sets `show_output: true`. A dedicated safety
case is recorded in `docs/authorized-operations.md`.

## Consequences

- The default registry and the Windows assessment pack remain read-only.
- High-impact actions are discoverable only after explicit opt-in, and are
  blocked by default scope even then.
- Every sensitive run carries an authorization reference in its event summary.
- The project's earlier "no credential dumping / remote execution" statements
  are scoped to the default configuration; docs and Sphinx/ADR references are
  updated to reflect the opt-in exception.
- No tools are installed, downloaded, or executed by importing the pack.
