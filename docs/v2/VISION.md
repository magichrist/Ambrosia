# Ambrosia v2 — Product Vision

## Core idea

Ambrosia v2 is a **fast, session-aware command launcher and executor workbench** for authorized security assessment and general operations. It is not a framework, not a blue-team-only tool, not a YAML DSL, and not a complex CLI. It is a single Textual TUI that lets an operator:

1. Register any shell command with a name, description, tags, and a shell template.
2. Search the catalog instantly by name, description, tags, or the shell command itself (full regex filter).
3. Select a command and run it — if its inputs were already provided in the current session it runs immediately; otherwise a small input form appears first.
4. See live output, cancel, and re-run with a keystroke.

It is built for **authorized use** (penetration testing, red teaming, sysadmin work, anything the operator is authorized to run). Ambrosia itself does not install, download, or bundle offensive tools — the operator brings the binaries (crackmapexec, nmap, impacket, etc.) and Ambrosia runs them through a shell with variable substitution.

## Example command

```text
name: windows version check smb
description: uses crackmapexec smb to get windows version
tags: ["smb", "windows", "crackmapexec", "windows version"]
inputs:
  - id: ip
    prompt: Target IP or hostname
    type: host
shell: crackmapexec smb {{ip}}
```

Operator types `smb` (or `crackmapexec`, or `windows version`) into the TUI search, the command surfaces, selects it, `crackmapexec smb 10.0.0.5` runs, output streams live.

## What v2 deliberately drops

- The v1 modular-monolith / application-service / repository layer.
- The `ambrosia/v1` preset YAML DSL and its variable grammar.
- The `engagement / scope / target / artifact / finding` domain model as the core.
- The multi-command Typer CLI surface (`ambrosia engagement create ...`, etc.).
- The policy engine, effect classes, approval state machine, and secret-reference protocol as primary features.
- Packs, manifests, and plugin protocols.

## What v2 keeps (simplified)

- A TUI-first experience (Textual).
- Shell command execution with `{{variable}}` substitution.
- Session memory: inputs typed once are remembered for the session.
- Search/filter with full regex across name, description, tags, and command.
- Authorized-use framing (operator is responsible for authorization; Ambrosia does not enforce entitlements).

## Non-goals for v2

- Distributed server, web UI, agents on targets.
- Artifact provenance chains, context-driven action suggestions, or execution history as a database of record.
- SOC2 / ISO / compliance tooling built in.
- Automatic vulnerability chaining or exploitation.
