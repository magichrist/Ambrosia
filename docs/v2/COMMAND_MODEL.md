# Ambrosia v2 — Command Model

## The command is the unit of work

Everything in v2 revolves around a `Command`. There are no presets, phases, actions, artifacts, or engagements. A command is a small record that tells Ambrosia:

- What to call it (name)
- What it does (description)
- How to find it (tags)
- What to run (shell template with `{{input}}` placeholders)
- What it needs before running (inputs)

## JSON representation

Commands are stored as simple JSON. Example `~/.ambrosia/commands.json`:

```json
[
  {
    "id": "smb-version",
    "name": "windows version check smb",
    "description": "uses crackmapexec smb to get windows version",
    "tags": ["smb", "windows", "crackmapexec", "windows version"],
    "shell": "crackmapexec smb {{ip}}",
    "inputs": [
      {
        "id": "ip",
        "prompt": "Target IP or hostname",
        "type": "host",
        "required": true,
        "secret": false
      }
    ]
  },
  {
    "id": "kerberoast",
    "name": "ad kerberoast",
    "description": "request service tickets for offline cracking",
    "tags": ["ad", "kerberos", "impacket", "credential_access"],
    "shell": "GetUserSPNs.py -dc-ip {{dc}} {{domain}}/{{user}}:{{password}} -request",
    "inputs": [
      { "id": "dc", "prompt": "Domain controller IP", "type": "host", "required": true },
      { "id": "domain", "prompt": "Domain name", "type": "string", "required": true },
      { "id": "user", "prompt": "Username", "type": "string", "required": true },
      { "id": "password", "prompt": "Password", "type": "secret", "required": true, "secret": true }
    ]
  }
]
```

## Shell template syntax

- `{{input_id}}` is replaced with the resolved value for that input.
- Only complete `{{...}}` tokens are substituted — no free-form interpolation.
- If a referenced input is missing or empty, the executor can either fail fast or leave the token (configurable per command).
- After substitution, the template is split into an argv array and run via `create_subprocess_exec` (no shell).

## Input types (hints only, not enforced)

| Type | Meaning |
|------|---------|
| `host` | IP address or hostname |
| `string` | free text |
| `path` | file system path |
| `integer` | whole number |
| `secret` | password / key — shown as hidden input, not logged in plaintext |

## Searchable fields

The TUI search matches (case-insensitive substring, or regex if wrapped in `/.../`):

- `name`
- `description`
- `tags` (joined by space)
- `shell` (the raw command template)

## Command lifecycle

1. **Register** — add to catalog (from JSON file or TUI "add command").
2. **Search** — operator types a query; catalog filters in real time.
3. **Select** — operator highlights a result and presses Enter.
4. **Resolve inputs** — if all required inputs have session values, offer to run immediately; otherwise show input form.
5. **Execute** — build argv, spawn subprocess, stream output.
6. **Remember** — input values are stored in session state keyed by command id.
