# Security model

Security is enforced in shared layers, never only in an interface.

## Authorization boundary

An **engagement** owns an explicit **scope**. An empty scope authorizes nothing.
Scope supports included hosts/CIDRs/domains, exclusions, permitted ports,
expiration, concurrency/rate limits, allowed effects, and approval requirements.
Every network action declares its target fields (`scope_fields`); the resolved
address is validated against the scope immediately before execution on every
path — CLI, TUI, and preset steps. A preset variable cannot expand the target
beyond the engagement scope.

## Effect classes

Actions declare effects from: `local_read`, `local_write`, `local_script`,
`network_observe`, `remote_read`, `authentication`, `remote_change`,
`credential_access`, `unknown`. The initial built-in pack uses only
`local_read` and `network_observe`. More sensitive classes are represented in
the policy model but unavailable in built-ins. Effects beyond read-only require
explicit approval (`require_approval_for` in scope).

## Approval

Approval is an explicit execution state (`awaiting_approval` → `ready` on grant,
`blocked` on deny). Approval records are persisted by engagement. The engine
never silently skips an approval requirement.

## Process execution

- `asyncio.create_subprocess_exec` with argv arrays; no shell, no `shell=True`.
- Executable is fixed by the action's registered `ExecutorReference` / dependency
  allowlist, never taken from untrusted preset input.
- Inputs are validated against the action's typed `input_schema` before argv is
  built; a token is either a literal argument or one complete typed reference.
- Output is streamed with a byte cap; timeouts and cancellation terminate and
  reap the child process.
- Exit code and duration are recorded; failures produce structured `FailedEvent`.

## Secrets

`SecretStore` is a Protocol in `domain/protocols.py`. Secrets are referenced
opaquely (`secrets.<name>` / `secret_ref`) and never stored as raw values in
YAML, SQLite, logs, exception messages, command previews, or evidence bundles.
Inputs named like credentials are rendered as password fields in the TUI, and
artifacts reject raw secret material in their `value`. No OS-backed secret
provider is bundled in v0.1; without a provider, secret values are not persisted.

## Preset safety

Presets are data validated into Pydantic models with `yaml.safe_load`. Unknown
fields are rejected, Python object tags are rejected, and there is no `eval`,
`exec`, pickle, arbitrary Jinja, loops, or dynamic import. Predicates are a
small constrained grammar. Dry-run resolves a deterministic plan and starts no
process. See `presets.md`.

## Auditability

Each execution records an operator, engagement, action/preset id, a redacted
input summary, scope decision, timestamps, result, and artifact references.
Events and state transitions are persisted so an interrupted job is visible as
unknown/interrupted on next startup rather than silently marked successful.

## Safety boundary of the built-in pack

The Windows assessment pack is read-only: Nmap XML service discovery and
SMB/LDAP/HTTP/RDP/WinRM configuration observation. It does not implement
credential extraction or replay, hash-based remote access, password spraying,
lateral movement, unauthorized remote command execution, persistence,
stealth/evasion, destructive actions, or exfiltration. HTTP methods and LDAP
hostnames are observations/heuristics, not proof of exploitability. Any
authentication-dependent capability requires a separate threat model and
explicit authorization design.

## Opt-in authorized operations

A separate `authorized-operations` pack (ADR-0012) wraps installed high-impact
binaries for explicitly authorized engagements. It is never enabled by default
and is governed by four independent gates: explicit registration, scope effect
allowlisting, a per-run authorization reference, and engine approval. Raw tool
output is not persisted by default. The full safety case, residual risks, and
output-handling rules are in `docs/authorized-operations.md`.
