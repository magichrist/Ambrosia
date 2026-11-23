# Ambrosia

A small Textual TUI for keeping shell commands in one searchable inventory and
running them from a single workstation. Presets are plain YAML files; workflows
group preset ids into ordered phases.

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ambrosia            # or: python -m ambrosia
```

From the repository root, `inventory/presets/` and `inventory/workflow/` load
automatically. Elsewhere, Ambrosia falls back to `~/.ambrosia/commands.json`.

Explicit options are available when needed:

```bash
ambrosia tui --preset-dir inventory/presets
ambrosia tui --preset-file inventory/presets/windows/cme-smb.preset
ambrosia tui --workflow-dir inventory/workflow
ambrosia workflow --workflow-dir inventory/workflow
ambrosia --help
```

## Features

- Three-panel workstation: library/tags, live search, and preset detail.
- Search by whole word or fragment, with `name:`, `cmd:`, `tag:`, `path:`, and
  `type:` qualifiers (`t:w` workflows, `t:p` presets, `t:a` both).
- Substring, fuzzy, and regex search modes (`ctrl+r` to cycle).
- Shared session values: set `target` once and every preset using `target`
  reuses it. Session values live in memory only.
- Workflows: group preset ids into phases and step through them with the arrow
  keys.
- Live output, cancellation, quick run, and run-again.

## Keys

| Key | Action |
|-----|--------|
| `/` | focus search |
| `↑` / `↓` | move result highlight |
| `Tab` | search → explorer → inspector |
| `Enter` | run preset / open workflow |
| `Esc` | clear filters / close modal / go back |
| `ctrl+r` | cycle search mode |
| `n` / `e` / `d` | add / edit / delete preset |
| `f` / `p` | favorite / pin |
| `x` | quick run |
| `g` / `c` / `b` | run again / cancel / back |
| `s` / `h` | session notice / history toggle |
| `ctrl+q` | quit |
| `?` | help |

Inside a workflow: `↑`/`↓` pick a command in the current phase, `Enter` runs it,
`→`/`←` move between phases, and `Esc` leaves.

## Inventory files

A preset is YAML. Its id comes from the path relative to the presets folder:
`windows/smb-check.preset` becomes `windows.smb-check`. The first folder is also
used as the category, so identically named files can live in different folders:

```yaml
# inventory/presets/windows/smb-check.preset
name: SMB Check
description: List SMB shares on a host.
tags: [windows, smb, inventory]
shell: "smbclient -L {{target}}"
inputs:
  - id: target
    prompt: "Target host"
    type: host
    required: true
```

Every `{{id}}` in `shell` should have a matching entry in `inputs`. Input flags
are `secret`, `default`, and `validation_hint`. The add-preset form (`n`) also
accepts a compact `id:prompt:flags` spec, where flags are `optional`, `secret`,
`host`, `path`, and `integer`.

A workflow lists preset ids under named phases; its filename stem is its id:

```yaml
# inventory/workflow/linux-recon.workflow
name: Linux Recon
description: Host, service, and web inventory commands.
phases:
  hosts:
    - linux.ping-check
    - linux.nmap-ping-sweep
  services:
    - linux.nmap.discovery
    - linux.ssh.version
```

Unknown preset ids are reported as "preset not found" in the runner. Workflows
are launchers; they do not auto-run a whole chain.

## Layout

| Path | Purpose |
|------|---------|
| `inventory/presets/` | `.preset` YAML files, grouped by folder |
| `inventory/workflow/` | `.workflow` phase chains |
| `~/.ambrosia/commands.json` | default JSON command catalog |
| `~/.ambrosia/scope.json` | optional CIDR policy |
| `~/.ambrosia/history.jsonl` | optional execution history |

Core modules: `ambrosia.model`, `ambrosia.storage`, `ambrosia.workflow`,
`ambrosia.executor`, and `ambrosia.tui`.

Commands are split on whitespace into an argv array and run without a shell, so
there is no quoting or piping inside a template.

## Check

```bash
ruff check src tests
mypy src
pytest -q
```
