# Ambrosia v2 — TUI Design

The TUI is the primary (and effectively only) interface. It is a single Textual application with three regions and a modal input form.

## Layout

```
╔══════════════════════════════════════════════════════════════════════════╗
║ Ambrosia v2  [session: default]  [commands: 47]  [running: 0]  [q]uit ║
╠══════════════════════════════════════════════════════════════════════════╣
║ [ search: smb______________________________ ] [regex: off]              ║
╠══════════════════════════════════════════════════════════════════════════╣
║ RESULTS                                                              ║   ║
║  ▸ windows version check smb                                          ║   ║
║    uses crackmapexac smb to get windows version                       ║   ║
║    tags: smb windows crackmapexec                                     ║   ║
║    shell: crackmapexac smb {{ip}}                                     ║   ║
║                                                                       ║   ║
║    ad kerberoast                                                      ║   ║ PREVIEW
║    request service tickets for offline cracking                       ║   ║
║    tags: ad kerberos impacket                                         ║   ║ ← full shell,
║    shell: GetUserSPNs.py ... {{dc}} {{domain}}/{{user}}               ║   ║   inputs
║                                                                       ║   ║
║ RESULTS                                                              ║   ║
╚══════════════════════════════════════════════════════════════════════════╝
```

- **Top bar**: app name, session name, command count, running jobs count, quit hint.
- **Search bar**: live filtering. `Tab` or `Enter` to move to results. `r` toggles regex mode.
- **Results list**: filtered commands. Each row shows name, description, tags, shell template. The highlighted row's full detail shows in the preview panel.
- **Preview panel** (right): full shell template, input list with prompts and types, saved session value if any.

## Keyboard bindings

| Key | Action |
|-----|--------|
| `/` or typing | focus search bar and filter |
| `Tab` | move focus between search and results |
| `Enter` | select highlighted command → resolve inputs / run |
| `Esc` | clear search / close modal / back |
| `r` | toggle regex mode on the search |
| `n` | add a new command (opens input modal) |
| `e` | edit the selected command |
| `d` | delete the selected command (confirm) |
| `s` | save session inputs for selected command (auto-saved on run) |
| `c` | cancel the currently running job |
| `q` | quit (confirm if a job is running) |
| `?` | help |

## Search behavior

- As the operator types, the results list filters immediately (debounced ~50ms).
- Plain text: case-insensitive substring match across name + description + tags + shell.
- Regex mode (`/pattern/` or toggled with `r`): full Python `re.search` against the same concatenated text. Invalid regex shows an inline error instead of crashing.
- Empty search shows all commands.

## Selecting and running a command

1. Operator highlights a command and presses `Enter`.
2. The app checks session state for that command's inputs:
   - **All required inputs present**: show a confirmation line "Run `crackmapexec smb 10.0.0.5`? (saved values)" — Enter runs, `e` edits inputs first.
   - **Some inputs missing**: open the input form with saved values pre-filled; empty required fields highlighted.
3. Input form: one line per input (`prompt: [ value ]`), secret inputs masked. `Enter` on the last field or `Run` button submits.
4. On submit: values are stored in session state, argv is built, subprocess spawns.

## Execution view

When a command runs, the TUI switches to a live-output view:

```
╔══════════════════════════════════════════════════════════════════════════╗
║ running: windows version check smb  [c]ancel  [b]ack                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║ crackmapexec smb 10.0.0.5                                             ║
║                                                                       ║
║ SMB         10.0.0.5      445    WINSERVER01   [+] Windows Server   ║
║                                                                       ║
║ (streaming output...)                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
```

- `c` cancels the job (terminates subprocess, reaps it).
- `b` returns to the results list (job keeps running in background; can be re-attached later if implemented).
- When the process exits, show exit code and duration, then offer "run again" or "back".

## Session state

- Keyed by command `id`.
- Stores `{ input_id: value }` for inputs the operator has provided.
- Persisted optionally to `~/.ambrosia/session.json` (or workspace-local `.ambrosia/session.json`) on exit and loaded on start.
- Secret inputs can be marked to not persist (operator choice).

## Adding / editing a command

A modal form collects: id, name, description, tags (comma-separated), shell template, and inputs (each: id, prompt, type, required, secret). Validation: id and name required, shell must contain at least one input reference or be a fixed command.

## What the TUI does NOT do

- No policy enforcement, scope checking, or approval state.
- No artifact tracking or provenance.
- No engagement/database concepts.
- No YAML preset loading or dry-run planning.
