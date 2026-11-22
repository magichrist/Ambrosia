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
- **Explorer**: debounced live search and ranked results. Rows are intentionally
  compact — `name: description` only. Hovering a row shows a tooltip with the
  full preset: id, path, tags, shell template, and inputs.
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
- Qualifiers: `name:`, `cmd:`, `tag:`, `path:`. Qualifiers and free text are
  ANDed; free text matches across name, command, tags, path, and description.
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
