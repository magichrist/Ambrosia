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
| `/` | focus the search bar |
| `↑` / `↓` | move through results while still typing in search |
| `Tab` | cycle focus (search → explorer → inspector) |
| `Enter` | select highlighted preset / run it |
| `Esc` | clear filters / close modal / back |
| `ctrl+r` | cycle search mode while typing (substring → fuzzy → regex) |
| `r` | cycle search mode when the explorer has focus |
| `n` | add a new preset |
| `e` | edit the selected preset |
| `d` | delete the selected preset (confirm) |
| `f` | toggle favorite on the selected preset |
| `p` | toggle pinned on the selected preset |
| `s` | save session inputs |
| `h` | toggle execution history logging (opt-in) |
| `S` | toggle scope policy (opt-in) |
| `c` | copy the compiled command / cancel the running job |
| `x` | quick run: run immediately and show a minimal result in the inspector |
| `g` | run the last command again |
| `b` / `←` | back from the execution view |
| `ctrl+q` | quit (confirm if a job is running) |
| `?` | show help |

The workstation has three panels: a **sidebar** (library views and tag filters),
an **explorer** (live search and ranked results), and an
**inspector** (full preset detail plus Run/Favorite/Pin controls). Search result
rows show only `name: description`; hover a row for tags, path, shell, and
inputs. Empty search shows all presets. Search matches whole words and word
fragments (`win` finds `windows`), and supports `name:`, `cmd:`, `tag:`, and
`path:` qualifiers.

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
- Session values are kept **in memory only** for the current run (shared by input name across presets) and wiped on quit; `~/.ambrosia/session.json` is not used by the TUI
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
