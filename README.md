# Ambrosia

**Fast TUI-first command launcher and executor workbench for authorized use.**

Ambrosia lets an operator register any shell command with a name, description,
tags, and a `{{input_id}}` shell template, then search and run it from a single
Textual TUI. Inputs are remembered per session, output streams live, and jobs
can be cancelled or re-run — all with zero CLI commands to memorize.

It is built for **authorized use** (penetration testing, red teaming, sysadmin
work, anything the operator is authorized to run). Ambrosia does not install,
download, or bundle offensive tools — the operator brings the binaries on PATH
and Ambrosia runs them through an argv array (no `shell=True`).

---

## Core example

Register `crackmapexec smb {{ip}}`, search `smb`, provide the IP, and watch
live output. The IP is remembered for next time.

```json
{
  "id": "smb-version",
  "name": "windows version check smb",
  "description": "uses crackmapexec smb to get windows version",
  "tags": ["smb", "windows", "crackmapexec"],
  "shell": "crackmapexec smb {{ip}}",
  "inputs": [
    { "id": "ip", "prompt": "Target IP or hostname", "type": "host", "required": true }
  ]
}
```

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Usage

Launch the TUI (the primary interface):

```bash
ambrosia
# or
python -m ambrosia
```

Optional flags:

```bash
ambrosia --commands-file builtin_commands.json
ambrosia --import-file my-commands.json
ambrosia --export-file my-backup.json
```

### Keyboard reference

| Key | Action |
|-----|--------|
| `/` | focus search bar |
| `Tab` | cycle focus (search → results → execution view) |
| `Enter` | select highlighted command / run again in execution view |
| `Esc` | clear search / close modal / back |
| `f` | cycle search mode (substring → fuzzy → regex) |
| `]` | cycle category filter |
| `F` | toggle favorites-only filter |
| `r` | toggle regex mode |
| `n` | add a new command |
| `e` | edit the selected command |
| `d` | delete the selected command (confirm) |
| `p` | toggle pinned on the selected command |
| `s` | save session inputs |
| `h` | toggle execution history logging (opt-in) |
| `S` | toggle scope allowlist (opt-in) |
| `c` | cancel the running job |
| `g` | run the last command again |
| `b` | back from the execution view |
| `q` | quit (confirm if a job is running) |
| `?` | show help |

---

## Built-in commands

The directory [`inventory/presets/`](inventory/presets/) contains commands
organized by OS subdirectory (``windows/``, ``linux/``). Each is a
human-writable YAML ``.preset`` file. Load them with:

```bash
ambrosia --preset-dir inventory/presets          # all OS presets
ambrosia --preset-dir inventory/presets/windows   # windows only
ambrosia --preset-file inventory/presets/windows/windows.smb.audit.preset  # single file
```

Or copy them into `~/.ambrosia/commands.json` to make them the default catalog.

The [`inventory/workflow/`](inventory/workflow/) directory is reserved for
workflow definitions. A ``.workflow`` file groups preset command ids into
ordered phases:

```yaml
name: Windows Gain Access
phases:
  reconnaissance:
    - windows.smb.audit
    - windows.nmap.discovery
    - windows.ldap.inventory
  exposure:
    - windows.rdp.exposure
    - windows.winrm.exposure
```

View workflows with:

```bash
ambrosia workflow --workflow-file inventory/workflow/windows-gain-access.workflow
ambrosia workflow --workflow-dir inventory/workflow
```

A ``.preset`` file looks like this:

```yaml
id: windows.smb.audit
name: SMB Configuration Audit
description: Read-only SMB configuration observation on target.
category: windows
tags:
  - windows
  - smb
  - read-only
shell: "crackmapexec smb {{target}}"
inputs:
  - id: target
    prompt: "Target IP or hostname"
    type: host
    required: true
    secret: false
    validation_hint: "must be an IP address or hostname within scope"
```

---

## Configuration

- `~/.ambrosia/commands.json` — command catalog (JSON)
- `~/.ambrosia/session.json` — remembered inputs per command (auto-saved)
- `~/.ambrosia/sessions/<name>.json` — named session files
- `~/.ambrosia/scope.json` — opt-in scope allowlist/denylist (CIDR-based)
- `~/.ambrosia/history.jsonl` — opt-in execution history log (JSONL)

Secrets are masked in the TUI and are **not persisted by default**.

---

## Verification

```bash
ruff check . && ruff format --check . && mypy src
pytest -q
ambrosia --help && python -m ambrosia --help
```

Tests use fake executors; no live target or Nmap installation is required.

---

## License

Apache License 2.0 — see `LICENSE`.
