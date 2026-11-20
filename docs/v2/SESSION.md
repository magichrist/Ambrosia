# Ambrosia v2 — Session & Input Memory

## Session state

A session is the lifetime of one TUI process. During that lifetime, Ambrosia remembers the values an operator types into each command's inputs.

```
session:
  commands:
    smb-version:
      ip: "10.0.0.5"
    kerberoast:
      dc: "10.0.0.10"
      domain: "corp.local"
      user: "svc_backup"
      # password intentionally not persisted
```

## How input memory works at run time

When a command is selected:

| Session state | Behavior |
|---------------|----------|
| All required inputs have values | Show "run with saved values?" — one keystroke to execute |
| Some required inputs missing | Open input form, pre-fill saved values, highlight empty required |
| No session values for this command | Open blank input form |

After a successful run, all provided input values are written into session state for that command id. The next time the same command is selected, it runs with one keystroke.

## Persistence (optional)

Session state can be written to a JSON file on exit and loaded on start:

- Default location: `~/.ambrosia/session.json`
- Workspace override: `.ambrosia/session.json` next to the commands file

This is a convenience, not a database of record. There is no execution history, no artifact store, no findings.

## Secret inputs

Inputs marked `secret: true` (passwords, keys) are:

- Masked in the input form.
- **Not persisted to the session file** by default (operator can opt in per command).
- Not written to logs or the terminal title.
- Still passed into the shell argv at execution time (the subprocess sees them).
