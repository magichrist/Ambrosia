# Authorized operations pack — safety case

The `authorized-operations` pack wraps installed Windows/AD red-team binaries
(Impacket, NetExec, samdump2) through Ambrosia's shell-free argv executor. It is
an **opt-in** capability that deliberately reverses the read-only default for
engagements that explicitly authorize high-impact testing. This document is the
"separately reviewed design and documented safety case" required by
`00_MASTER_PLAN.md` §3/§10.4 before such capabilities can exist.

## 1. Scope of the capability

| Capability | Action id | Installed binary |
|---|---|---|
| SAM/NTDS credential extraction | `windows.credentials.secretsdump` | `secretsdump.py` |
| Offline SAM hive hash extraction | `windows.credentials.samdump2` | `samdump2` |
| SMB/AD authentication and enumeration | `windows.smb.netexec` | `netexec` |
| Remote command execution (NetExec) | `windows.lateral.netexec_exec` | `netexec` |
| Remote command execution (Impacket) | `windows.lateral.psexec` | `psexec.py` |
| AD user enumeration | `windows.ad.domain_enumeration` | `GetADUsers.py` |
| AD AS-REP roast | `windows.ad.asrep_roast` | `GetNPUsers.py` |
| AD Kerberoast | `windows.ad.kerberoast` | `GetUserSPNs.py` |
| AD SID enumeration | `windows.ad.sid_enumeration` | `lookupsid.py` |
| NTLM → SMB relay | `windows.smb.ntlm_relay` | `ntlmrelayx.py` |

Ambrosia does **not** install, download, bundle, or execute these tools during
registration or import. The operator must have them on PATH on the machine
running the assessment. Availability is a metadata/PATH check only.

## 2. Four independent gates

A high-impact run requires all of the following:

1. **Explicit opt-in registration.** `build_registry()` and production service
   startup never register this pack. The operator must call
   `register_authorized_operations(registry)` explicitly. The default registry
   therefore never suggests these actions.
2. **Scope effect allowlisting.** These actions declare `credential_access`,
   `remote_change`, and/or `authentication` effects. A default scope allows
   only `local_read` and `network_observe`, so the availability matcher blocks
   them until the operator explicitly widens `allowed_effects`.
3. **Per-run authorization reference.** `AuthorizationService` (application
   layer) and `require_request_authorization` (handler layer) both require a
   non-empty authorization reference for every run. CLI uses `--authorization`;
   the TUI has an "Authorization reference" input in action details. The
   reference is included in the sanitized event summary for attribution.
4. **Approval state.** The engine's `request_approval()` requires an explicit
   approval grant for `credential_access`/`remote_change` actions before a job
   can reach `ready`.

Scope targeting is still enforced immediately before execution, so a target
outside the engagement scope cannot be relayed to, dumped, or executed against.

## 3. Output and secret hygiene

- `show_output` defaults to **false**. By default the handler emits only
  metadata (tool, target, exit code, output byte count, authorization
  reference). Raw tool output is never persisted to SQLite or artifacts.
- Setting `show_output: true` explicitly opts in to emitting raw output as an
  execution event, which the engine persists. This may contain hashes or other
  credential material. It is documented as a deliberate operator choice and
  should be used only in controlled engagements.
- No credential values are accepted as action inputs that get logged: keys
  named `password`, `secret`, `token`, `key`, `credential`, and `hash` are
  redacted from execution input summaries by the engine.
- The reserved `authorization_reference` input is never forwarded into tool
  argv.

## 4. Execution safety

- All execution goes through `ProcessExecutor` (`asyncio.create_subprocess_exec`,
  argv arrays, no shell). Each action's executable is fixed by its action
  definition, never taken from untrusted input.
- `extra_args` is validated as a list of strings passed as separate argv values.
  Shell metacharacters are data, not interpreted.
- Timeouts (default 300s), output byte caps, cancellation, and child reaping are
  inherited from the shared executor.
- No automatic retries. No persistence, stealth, or evasion features.

## 5. Residual risks and limitations

- These tools can cause real, state-changing effects on target systems. Ambrosia
  cannot verify that the operator holds valid authorization; the gates ensure
  the operator explicitly asserted it and that the run is attributable.
- NTLM relay requires a listener and favourable network conditions; Ambrosia
  only invokes the tool and does not manage relay logistics.
- Verbose tool output may include sensitive data in the operator's terminal even
  when `show_output` is false; the terminal session is the operator's
  responsibility.
- The tools themselves may behave differently across versions. Pin and review
  the binaries on the assessment machine.

## 6. Decision record

See `docs/decisions/0012-authorized-operations-pack.md`.
