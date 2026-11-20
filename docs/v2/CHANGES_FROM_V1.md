# Ambrosia v2 — What Changed from v1

| Dimension | v1 (current) | v2 (reconstruction) |
|-----------|--------------|---------------------|
| Primary interface | Typer CLI + Textual TUI | Textual TUI only |
| Unit of work | Action → Preset → Engagement | Command |
| Command definition | Pydantic `ActionDefinition` + pack manifest | Simple JSON record (name, description, tags, shell, inputs) |
| Variable language | `ambrosia/v1` preset YAML with `{{ namespace.path }}` grammar | `{{input_id}}` shell template substitution only |
| Search | Action matcher with context/artifact requirements | Regex/substring filter across name, description, tags, shell |
| Input memory | Context artifacts + execution history | Session dictionary keyed by command id |
| Storage | SQLite + SQLAlchemy + Alembic | Optional JSON file (commands + session) |
| Safety enforcement | Policy engine, scope, effects, approvals, secret references | None by default; operator responsible |
| Tools bundled | None (binaries on PATH) | None (binaries on PATH) |
| Blue-team framing | Read-only first, opt-in high-impact pack | General purpose; authorized use by operator |

## Why the change

v1 was designed as a context-driven automation workbench with a safety-first, blue-team-oriented architecture: engagements, scopes, artifacts, policy engines, approval state machines, and a declarative preset DSL. That is a heavy, framework-like system.

The requested v2 is the opposite: a **fast command launcher**. The operator wants to register `crackmapexec smb {{ip}}`, search for it, and run it — with remembered inputs — all inside a TUI. There is no need for engagements, scopes, presets, or YAML.

v2 keeps the Textual TUI and shell execution from v1 but strips everything else down to the command model.

## What survives from v1

- Textual as the UI toolkit.
- `asyncio.create_subprocess_exec` (no `shell=True`) for process execution.
- `{{variable}}` template substitution (simplified grammar).
- The idea that the operator brings their own tools (nothing installed or bundled).
