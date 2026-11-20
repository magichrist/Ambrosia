# Ambrosia v2 — Design Docs

This directory contains the reconstruction plan for Ambrosia v2: a fast, TUI-first command launcher and executor workbench for authorized use (penetration testing, sysadmin, red team, anything the operator is authorized to run).

## Reading order

1. `VISION.md` — product vision and core idea
2. `ARCHITECTURE.md` — three-layer structure (TUI → catalog → executor)
3. `COMMAND_MODEL.md` — the command record (name, description, tags, shell, inputs) and JSON format
4. `TUI.md` — layout, keyboard bindings, search, execution view
5. `SESSION.md` — session state and input memory
6. `SAFETY.md` — authorized-use framing and shell safety
7. `ROADMAP.md` — phased reconstruction plan
8. `CHANGES_FROM_V1.md` — what was dropped and why

## Core example

```json
{
  "id": "smb-version",
  "name": "windows version check smb",
  "description": "uses crackmapexec smb to get windows version",
  "tags": ["smb", "windows", "crackmapexec", "windows version"],
  "shell": "crackmapexec smb {{ip}}",
  "inputs": [
    { "id": "ip", "prompt": "Target IP or hostname", "type": "host", "required": true }
  ]
}
```

Operator searches `smb` in the TUI, selects it, provides `ip` (or uses the remembered session value), and `crackmapexec smb 10.0.0.5` runs with live output.

## What v2 is not

- Not blue-team only.
- Not a YAML preset DSL.
- Not an engagement/scope/artifact framework.
- Not a policy engine or approval state machine.
- Not a Typer CLI with many subcommands.

It is a command launcher. Fast, session-aware, TUI-driven.
