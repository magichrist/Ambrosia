# ADR 0010 — Domain-neutral core, read-only Windows-first pack

- Status: Accepted
- Date: 2026-11-20

## Context

The initial use case is Windows/Active Directory assessment, but Ambrosia is
meant to support other domains (network inventory, web, Linux, operations).

## Decision

Core models and engines are domain-neutral. Windows/AD is supplied as the first
built-in pack (`windows-assessment`) with read-only discovery and configuration
observation. The pack declares Nmap service-name aliases explicitly and uses a
structured XML parser rather than human-readable output.

## Consequences

- New domains can be added as packs without editing core engine code.
- The first pack is safe, auditable, and testable with fixtures.
- Credential theft/replay, spraying, lateral movement, persistence, evasion,
  and exfiltration are excluded and require a separate safety case.
- LDAP domain identification is a documented hostname heuristic, not an
  authoritative directory query.
