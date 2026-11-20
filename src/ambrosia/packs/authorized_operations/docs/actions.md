# Actions

All actions require `authorization_reference` and an expanded scope
`allowed_effects`. `show_output` defaults to false; enabling it persists raw
tool output in execution history.

| Action id | Binary | Effects | Scope fields |
|---|---|---|---|
| `windows.credentials.secretsdump` | `secretsdump.py` | `credential_access` | `target` |
| `windows.credentials.samdump2` | `samdump2` | `credential_access` | (offline hives) |
| `windows.smb.netexec` | `netexec` | `authentication`, `remote_read` | `target` |
| `windows.lateral.netexec_exec` | `netexec` | `remote_change` | `target` |
| `windows.lateral.psexec` | `psexec.py` | `remote_change` | `target` |
| `windows.ad.domain_enumeration` | `GetADUsers.py` | `authentication`, `remote_read` | `target` |
| `windows.ad.asrep_roast` | `GetNPUsers.py` | `credential_access` | `target` |
| `windows.ad.kerberoast` | `GetUserSPNs.py` | `credential_access` | `target` |
| `windows.ad.sid_enumeration` | `lookupsid.py` | `authentication`, `remote_read` | `target` |
| `windows.smb.ntlm_relay` | `ntlmrelayx.py` | `credential_access`, `remote_change` | `target` |

## Common inputs

- `authorization_reference` (required) — rules-of-engagement or ticket id.
- `show_output` (optional, default false) — emit raw output as a persisted event.
- `extra_args` (optional) — additional flags as separate argv strings.

## Tool-specific inputs

- secretsdump: `target`, optional `username`, `password`, `no_pass`.
- samdump2: `system_hive`, `sam_hive` (paths to previously acquired hives).
- NetExec: `target`, `protocol` (`smb`/`ldap`/`http`), optional credentials.
- NetExec exec / psexec: `target`, `command`, optional credentials/domain.
- AD enumeration: `target`, optional `domain` and credentials.
- AS-REP roast: `target` (DC IP), `domain`, optional credentials.
- Kerberoast: `target`, optional `domain` and credentials.
- SID enumeration: `target`, optional credentials/domain.
- NTLM relay: `target` (relayed to `smb://<target>`).

Executable names are fixed by each action definition and are never derived from
input. On distributions where NetExec is invoked as `nxc`, provide a wrapper or
alias on PATH named `netexec`; Ambrosia does not guess executable names.
