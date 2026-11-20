# Ambrosia v2 — Safety & Authorized Use

## Framing

Ambrosia v2 is **not blue-team only** and is not restricted to defensive use. It is a general command launcher/executor workbench. The operator is responsible for ensuring they are authorized to run any command against any target.

Ambrosia itself:

- Does **not** install, download, or bundle offensive or security tools.
- Does **not** enforce entitlements, licensing, or scope.
- Does **not** validate that an operator has written authorization for a target.

The operator brings the binaries (crackmapexec, nmap, impacket, evil-winrb, etc.) and Ambrosia runs them.

## Shell execution safety

- Commands run via `asyncio.create_subprocess_exec` with an argv array — **no `shell=True`**.
- The shell template is split into arguments after `{{variable}}` substitution. Shell metacharacters in input values are passed as data, not interpreted by a shell.
- The executable comes from the command's registered `shell` template, not from untrusted operator input at runtime (the operator defines the template when registering the command).
- Output is streamed with a byte cap; timeouts and cancellation terminate and reap the child process.

## Secret handling

- Secret inputs are masked in the TUI and not persisted to the session file by default.
- Secret values are still passed into the subprocess argv (the tool needs them).
- Raw tool output may contain credentials or hashes — that is the operator's responsibility to handle in a controlled engagement.

## What is NOT enforced (by design)

- No scope allowlist (include/exclude targets).
- No approval state machine.
- No authorization-reference requirement.
- No effect classification (read-only vs. credential_access vs. remote_change).

If an organization needs those controls, they can be added as a thin wrapper around the executor in a later version, but they are not part of v2's core.

## Responsibility statement

The operator is solely responsible for:

- Obtaining written authorization before running commands against targets.
- Ensuring tools on PATH are legitimate and version-pinned.
- Handling any output that contains sensitive material.
- Complying with applicable laws and rules of engagement.
