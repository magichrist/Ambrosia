# ✦ Ambrosia

*A warm little command launcher for work you're authorized to do.*

Ambrosia keeps your favorite shell commands in one Textual TUI: name them, tag them,
search them, and run them with live output. Inputs are shared across presets for
the whole session, and workflows can chain presets into ordered phases.

It is built for **authorized use** — pentesting, red teaming, sysadmin work,
anything you're allowed to run. Ambrosia does not install or bundle tools; you
bring the binaries on `PATH`, and Ambrosia runs them as an argv array (never
`shell=True`).

---

## ✧ At a glance

- **Three-panel workstation** — library/tags on the left, live search in the middle,
  full preset detail on the right.
- **Fast search** — whole words and fragments (`win` → `windows`), with
  `name:`, `cmd:`, `tag:`, `path:`, and `type:` qualifiers.
- **Shared session values** — set `target` once; every preset with a `target`
  input reuses it until you quit. Nothing is written to disk.
- **Workflows** — group preset ids into phases, then step through them with the
  arrow keys and run any command from its phase.
- **Gentle execution** — streamed output, cancellation, quick run, history and
  optional CIDR scope checks.

---

## ♡ Get started

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Launch the TUI — no subcommand needed:

```bash
ambrosia            # or: python -m ambrosia
```

Explicit subcommands are still available when you want them:

```bash
ambrosia tui --preset-dir inventory/presets
ambrosia tui --preset-file inventory/presets/windows/cme-smb.preset
ambrosia tui --workflow-dir inventory/workflow
ambrosia tui --workflow-file inventory/workflow/linux-recon.workflow
ambrosia tui --import-file my-commands.json
ambrosia tui --export-file my-backup.json
ambrosia workflow --workflow-dir inventory/workflow
ambrosia --help
```

Running from the repository root auto-loads `inventory/presets/` and
`inventory/workflow/`. Elsewhere, the TUI falls back to
`~/.ambrosia/commands.json`.

---

## ⌨ The workstation

| Key | Action |
|-----|--------|
| `/` | focus the search bar |
| `↑` / `↓` | move the result highlight while typing |
| `Tab` | cycle focus: search → explorer → inspector |
| `Enter` | run the highlighted preset / open a workflow |
| `Esc` | clear filters / close a modal / go back |
| `ctrl+r`, `r` | cycle substring → fuzzy → regex search |
| `n` / `e` / `d` | add / edit / delete a preset |
| `f` / `p` | toggle favorite / pinned |
| `x` | quick run: minimal result in the inspector |
| `g` / `c` / `b` | run again / copy or cancel / back |
| `h` / `S` | toggle history / scope (both opt-in) |
| `s` | show the in-memory session notice |
| `ctrl+q` | quit (confirm if a job is running) |
| `?` | help |

Search accepts `name:`, `cmd:`, `tag:`, `path:`, and `type:` qualifiers. Use
`t:w` for workflows, `t:p` for presets (the default), or `t:a` for both.

When a workflow is open, `↑`/`↓` pick a command in the current phase,
`Enter` runs it, `→` advances a phase, and `←` steps back — or exits on
phase 1, just like `Esc`.

Pressing `n` opens the add-preset form. Write the command in **Command template**
with `{{name}}` placeholders; one input is created for each. The optional
**Input overrides** field uses `id:prompt:flags` entries separated by commas,
with `+`-separated flags `optional`, `secret`, `host`, `path`, `integer` —
for example `target:Target IP:host, password::secret`.

---

## ⟡ Writing presets and workflows, briefly

### A preset (`.preset`)

Drop a YAML file into `inventory/presets/` (subdirectories are fine).
**The filename stem is the id** — an `id:` key inside the file is ignored.

```yaml
# windows/smb-check.preset  ->  id: smb-check
name: SMB check
description: Read-only SMB observation on a target.
category: windows
tags: [windows, smb, read-only]
shell: "crackmapexec smb {{target}}"
inputs:
  - id: target
    prompt: "Target IP or hostname"
    type: host
    required: true
    validation_hint: "IP or hostname within scope"
```

Every `{{id}}` in `shell` should have a matching entry in `inputs`, otherwise
the placeholder stays literal when the command runs. Optional input keys:
`secret`, `default`, `validation_hint`.

### A workflow (`.workflow`)

Drop a YAML file into `inventory/workflow/`. Again, **the filename is the id**.
List preset ids under named phases, in the order you want them offered.

```yaml
# linux/recon.workflow  ->  id: recon
name: Linux recon
description: A small read-only chain.
phases:
  discovery:
    - nmap.discovery
    - ssh.version
  follow-up:
    - http.observation
```

Find it with `t:w`, press `Enter`, and walk the phases with the arrow keys.
Unknown preset ids are shown as "preset not found" in the runner.

---

## ☾ Session and execution behavior

- Input values live in memory, keyed by **input name**, so any preset sharing
  `target` inherits the value. Quitting (`ctrl+q`) wipes everything; no session
  file is written or loaded by the TUI.
- `Enter` shows a confirmation with the compiled argv; `x` skips it and reports a
  one-line status in the inspector.
- Secret inputs are masked in the inspector and forms.
- Each job streams output in the execution view; `c` cancels a running job,
  `b` / `←` comes back to the workstation (or to the same workflow phase).

---

## ◈ Where things live

| Path | Purpose |
|------|---------|
| `inventory/presets/` | human-writable `.preset` files |
| `inventory/workflow/` | `.workflow` phase chains |
| `~/.ambrosia/commands.json` | default JSON command catalog |
| `~/.ambrosia/scope.json` | opt-in CIDR allow/deny policy |
| `~/.ambrosia/history.jsonl` | opt-in execution history |

Core modules: `ambrosia.model` (record shapes), `ambrosia.storage` (JSON and
`.preset` loading), `ambrosia.workflow` (workflow loading), `ambrosia.executor`
(argv substitution + subprocess), and `ambrosia.tui` (the Textual app).

---

## 🧪 Verification

```bash
ruff check src tests
mypy src
pytest -q
```

Tests use fake executors, so no live target or installed Nmap is required.

---

## ⚠ Known limitations

- Commands are split on whitespace into argv; there is no shell quoting or
  piping inside a template.
- With scope enforcement enabled, targets must be IP addresses — hostnames are
  reported as "target is not an IP address".
- `s` is informational only: the session is memory-only and dies with the app.
- Workflows are launchers for presets; they do not auto-run a whole chain.

---

## License

Apache License 2.0 — see `LICENSE`.
