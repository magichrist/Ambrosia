# Ambrosia v2 — Architecture

## High-level structure

A single Python application with three logical layers:

```
+-------------------------------------------+
|         Textual TUI (the only UI)         |
|  search bar  |  results list  | preview   |
+--------------+---------------+-------------+
|              Command Catalog (in memory)  |
|  name, desc, tags, shell template, inputs |
+-------------------------------------------+
|             Session State (in memory)     |
|  last-used inputs per command id          |
+-------------------------------------------+
|             Shell Executor                |
|  subprocess_exec (argv), {{var}} replace  |
+-------------------------------------------+
```

## Dependency direction

`tui` → `catalog` → `executor`. That's it. No storage layer, no application services, no domain models, no policy engine.

## Core components

### 1. Command Catalog

A plain in-memory list of `Command` definitions. Commands can be loaded from a simple JSON file (`~/.ambrosia/commands.json` or a workspace file) or registered at runtime through the TUI.

No YAML DSL. No Pydantic validation beyond basic sanity. Commands are data.

### 2. Search & Filter

The TUI search bar accepts a string. The catalog is filtered in real time:

- Match against `name`, `description`, `tags` (joined), and `shell`.
- **Full regex support**: if the query is wrapped in slashes (e.g. `/smb.*windows/`), it's treated as a Python `re` search against the concatenated searchable text. Otherwise it's a case-insensitive substring match.

### 3. Shell Executor

Uses `asyncio.create_subprocess_exec` with an argv array built from the shell template:

```
shell: crackmapexec smb {{ip}}
inputs: { ip: "10.0.0.5" }
argv: ["crackmapexec", "smb", "10.0.0.5"]
```

- `{{name}}` tokens are replaced with the resolved input value.
- Tokens that don't match any input are left as-is (or cause a warning).
- No `shell=True`. The shell template is split into argv by whitespace after substitution (simple split, sufficient for the intended use; quoted args can be added later).
- Output streams live to a Textual log widget.
- Cancellation terminates and reaps the child process.

### 4. Session State

A simple dictionary: `command_id -> { input_id: value }`. When a command is selected:

- If all required inputs have session values → run immediately (or offer a "run with saved values" choice).
- If any required input is missing → show an input form pre-filled with saved values where available.

Session state lives in memory for the lifetime of the TUI process. Optional: persist to a JSON file on exit / load on start.

### 5. Command definition (in-memory model)

```python
class CommandInput:
    id: str          # e.g. "ip", "target", "user_list"
    prompt: str      # e.g. "Target IP or hostname"
    type: str        # hint: host, string, path, integer, secret
    required: bool   # default True
    secret: bool     # default False -> shown as password in TUI

class Command:
    id: str          # stable identifier (slug of name, or explicit)
    name: str
    description: str
    tags: list[str]
    shell: str       # template with {{input_id}} placeholders
    inputs: list[CommandInput]
```

## What is NOT in v2 architecture

- No SQLAlchemy, no Alembic, no SQLite by default.
- No `Engagement`, `Scope`, `Target`, `Artifact`, `ExecutionRecord`, `Finding`.
- No `PolicyEngine`, `EffectClassifier`, `ApprovalService`.
- No `PresetDefinition`, `PresetStep`, `DryRunResult`.
- No `Registry`, `PackManifest`.
- No `ActionHandler` protocol with `AsyncIterator`.
- No Typer CLI as the primary interface (a minimal CLI may exist just to launch the TUI).
