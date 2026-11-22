# Ambrosia v2 — TUI Design

The TUI is the primary interface. It is a single Textual application with a
three-panel workstation, a full-screen execution view, and modal dialogs.

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ AMBROSIA / PRESET WORKSTATION  ● READY  PRESETS 47  RESULTS 12 [?][^Q] │
├──────────────┬───────────────────────────────────┬──────────────────────┤
│ LIBRARY      │ [SUBSTRING] search ...            │ PRESET INSPECTOR     │
│ [ALL]        │ search mode: substring (ctrl+r)   │ nmap scan            │
│ [FAVORITES]  │                                   │ id: windows.nmap     │
│ [PINNED]     │ nmap scan: Discover open ports    │ description ...      │
│ [RECENT]     │ whois lookup: Look up domain      │ path: pr.windows     │
│ TAGS         │                                   │ tags: [nmap] [...,]  │
│ ○ OR ● AND   │                                   │ shell                │
│ ☐ nmap [12]  │                                   │ nmap -sV {{target}}  │
│ ☐ smb  [8]   │                                   │ inputs               │
│              │                                   │ [target] Target: ... │
│              │                                   │ [ RUN ] [FAV] [PIN]  │
│              │                                   │                      │
├──────────────┴───────────────────────────────────┴──────────────────────┤
│ /:search Tab:focus Enter:run Esc:back ^R:mode x:quick c:copy g:again…│
└──────────────────────────────────────────────────────────────────────────┘
```

- **Top bar**: session status (`READY`/`RUNNING`), preset/result counts, and
  active tag/scope indicators.
- **Sidebar**: `ALL`, `FAVORITES`, `PINNED`, `RECENT` library views and tag
  checkboxes with an OR/AND mode toggle.
- **Explorer**: debounced live search and ranked results. Preset rows are
  intentionally compact — `name: description` only. Workflow rows are marked
  `[workflow]` and show their phase/command counts. Hovering a row shows a
  tooltip with the full preset (id, path, tags, shell template, inputs) or the
  full workflow (id, description, ordered phases with command ids).
- **Inspector**: full detail for the highlighted preset plus `RUN`, `FAVORITE`,
  and `PIN` buttons. It is populated automatically from the first result, so
  `Enter` works without an initial arrow key.

## Keyboard bindings

| Key | Action |
|-----|--------|
| `/` | focus the search bar |
| `↑` / `↓` | move the result highlight while typing (no Enter needed) |
| `Tab` | cycle focus: search → explorer → inspector |
| `Enter` | select / run the highlighted preset |
| `Esc` | clear filters / close modal / back |
| `ctrl+r` | cycle search mode while typing |
| `r` | cycle search mode when the explorer has focus |
| `n` / `e` / `d` | add / edit / delete a preset |
| `f` / `p` | toggle favorite / pinned on the selected preset |
| `i` / `E` | import / export presets |
| `s` | save the session |
| `h` / `S` | toggle history logging / scope policy |
| `c` | copy the compiled command or cancel the running job |
| `x` | quick run (stays on the workstation; minimal result in the inspector) |
| `g` | run the last command again |
| `b` / `←` | back from the execution view |
| `ctrl+q` / `?` | quit / help |

## Search behavior

- Filtering is debounced (~75 ms). Empty search shows all presets.
- Modes: substring (default), fuzzy (character subsequence), and regex.
- Free text matches whole words and word fragments: `win` finds `windows`, and
  a match at a word boundary ranks ahead of a match buried inside a word.
- Qualifiers: `name:`, `cmd:`, `tag:`, `path:`, `type:`. Qualifiers and free text
  are ANDed; free text matches across name, command, tags, path, and description.
- `type:` selects the result kind: `preset` (default), `workflow`, or `all`.
  The short form `t:` works identically, with value aliases: `t:p`, `t:w`, `t:a`
  (e.g. `t:w` is the same as `type:workflow`). Workflow definitions are loaded
  from `inventory/workflow/` at startup (override with `--workflow-dir` /
  `--workflow-file`). With `t:w` / `type:workflow`, library views and tag filters
  are ignored because they apply only to presets.
- Invalid regex is reported inline in the search status line instead of
  silently returning zero results.

## Selecting and running a preset

1. The first result is selected automatically; arrow keys or clicking change it.
2. `Enter` (or the inspector's `RUN` button) resolves inputs from the in-memory
   session. Values are shared by input name across presets: setting `target`
   once means every other preset with a `target` input reuses it.
   - all required inputs present → confirmation modal with `Run` / `Edit inputs` / `Cancel`;
   - missing required inputs → input form pre-filled with shared values.
3. Secret inputs are masked.
4. On submit, argv is built and the subprocess starts in the execution view.
5. The session lasts only until you quit (`ctrl+q`); it is never written to disk
   and all values are wiped on exit.

## Running a workflow

`Enter` on a workflow row (or search `type:workflow` and press `Enter`) opens the
phased workflow runner instead of the inspector. It starts on phase 1:

- `↑` / `↓` select a command id in the current phase. Rows show the resolved
  preset name and id; ids without a matching preset are marked "preset not found".
- `Enter` runs the selected command through the normal confirmation/input flow.
  Completed commands appear in the execution view as usual.
- `→` moves to the next phase (clamped at the last phase); `←` moves to the
  previous phase, and on phase 1 it acts like `Esc` and returns to the main TUI.
- `b` / `Esc` leaves the runner and returns to the preset workstation.
- After a command finishes, `b` / `←` in the execution view returns to the same
  workflow phase with the same command highlighted.

## Adding and editing presets

`n` opens the Add preset form and `e` reopens it for the selected preset. The
command template is written with `{{name}}` placeholders, e.g.
`nmap -sV {{target}}`; one input is derived from each unique placeholder in the
order it appears. Optional **Input overrides** customize the derived inputs
using comma-separated `id:prompt:flags` entries. Flags are `+`-separated and may
include `optional`, `secret`, and a type hint (`host`, `path`, `integer`); the
default is a required, non-secret string. Existing definitions are preserved
when editing unless explicitly overridden, and placeholders added to the shell
template become new inputs automatically.

## Execution view

While a job runs, the top bar and workstation are hidden and the execution view
fills the screen: a running header, the compiled command, a scrolling live log,
a colour-coded status line (exit code and duration), and a `Run again` button.
`c` cancels the job; `b` or `←` returns to the workstation while the job keeps
running.

## What the TUI does NOT do

- No artifact tracking, provenance, or engagement/database concepts.
- No YAML preset authoring inside the TUI (use the CLI / `.preset` files).
- No dry-run planning or workflow execution.
