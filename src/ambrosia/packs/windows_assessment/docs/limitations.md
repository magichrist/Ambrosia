# Windows assessment pack — limitations and safety boundary

This document describes the explicit limitations of every module in the
`windows-assessment` pack (pack id `windows-assessment`, version 1.0.0). It is
part of the pack's safety contract and should be reviewed before enabling the
pack in any engagement.

## Safety boundary (non-negotiable)

All actions in this pack are **read-only discovery and configuration
observation**. None of the following are implemented, and none will be added
without a separately reviewed design, explicit authorization requirements, and
a documented safety case:

- Credential extraction, credential replay, or hash-based remote access.
- Password spraying or any authentication brute-force.
- Lateral movement or unauthorized remote command execution.
- Persistence mechanisms.
- Stealth, evasion, or anti-forensic techniques.
- Destructive actions or data exfiltration.

Authentication-dependent modules are deliberately kept out of the initial
built-in pack and require separate review (see
docs/00_MASTER_PLAN.md 3 and 10.4).

## Declared effects

Every action declares only `network_observe` (bounded, declared network
discovery). The default engagement scope permits `local_read` and
`network_observe`, so these actions are policy-permitted by default; actions
requiring `local_write`, `remote_change`, `authentication`, or
`credential_access` are blocked by policy in v0.1.

## Module-specific limitations

### network.nmap.service_discovery

- Scans only the ports declared in the `ports` input on a single in-scope
  target. It is not a full network sweep.
- Output is parsed from Nmap XML (`-oX -`) only. Nmap's human-readable console
  and grepable output are never parsed.
- Service identification (`-sV`) relies on banner/service fingerprinting and
  may misidentify services; `service_name`/`product`/`version` are best-effort
  observations, not authoritative identity.
- Hosts that do not respond are still treated as up (`-Pn`); absence of a
  service record does not prove a port is closed.

### windows.smb.configuration_audit

- Requires a previously discovered SMB `network.service` artifact on the same
  target (same_target matching). It cannot run against a host with no known
  SMB service.
- Reads SMB protocol version, domain, forest, and server role from Nmap SMB
  script output (`smb-protocols`, `smb-os-discovery`, `smb-security-mode`).
- Script output is free-form text embedded in structured XML; only
  well-known `key: value` lines are recognized.
- Never extracts credentials, never performs session setup or authentication,
  and never modifies SMB settings. Remediation guidance is text metadata only.

### windows.ldap.domain_inventory

- Requires a previously discovered LDAP `network.service` artifact on the same
  target.
- Observes LDAP service metadata only. Directory domain/forest is inferred
  best-effort from service hostnames (a heuristic), not from an authoritative
  directory query. No LDAP bind, search, or authentication is performed.
- Never accesses directory data or credentials.

### windows.http.method_observation

- Requires a previously discovered HTTP `network.service` artifact on the same
  target.
- Uses the Nmap `http-methods` script to enumerate **advertised** methods.
- **Advertised HTTP methods are observations and do not prove exploitability.**
  The presence of PUT, DELETE, TRACE, or any other method is not, by itself, a
  finding or evidence of a vulnerability.
- Never performs upload, injection, fuzzing, or mutation testing. No request
  body is ever sent.

### windows.rdp.exposure_observation

- Requires a previously discovered RDP `network.service` artifact on the same
  target.
- Observes the RDP security layer from Nmap script output. Never attempts
  authentication, credential replay, or remote command execution.
- Exposure observation is not a finding by itself.

### windows.winrm.exposure_observation

- Requires a previously discovered WinRM `network.service` artifact on the same
  target.
- Observes WinRM transport/authentication settings from Nmap script output.
- Never attempts authentication or remote command execution.
- Exposure observation is not a finding by itself.

## Remediation guidance

Remediation guidance is provided as text metadata on observation artifacts
only. Ambrosia never automatically modifies target settings based on pack
output; any configuration change remains a manual, operator-controlled,
authorized operation.

## Scope enforcement

Every network action declares `scope_fields: [target]` so its target is
validated against the engagement scope at execution time. Targets outside the
authorized scope are blocked before any tool runs.
