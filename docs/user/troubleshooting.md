# Troubleshooting

## "No network action is available"

An empty scope authorizes nothing. Run `ambrosia scope show` and add the target
or CIDR with `ambrosia scope update --include-host` / `--include-cidr`. Check
`ambrosia actions check <action-id>` for the exact reason.

## "Action is blocked / missing dependency"

`ambrosia actions check <action-id>` prints the reason list. A `blocked` status
means scope or policy refused it; `missing_dependency` means a declared local
tool (for example `nmap`) was not found on PATH. The built-in pack declares tool
requirements as metadata and does not run tools during registration.

## "Preset validation failed"

Run `ambrosia preset validate <path>` and read the structured error list.
Common causes: duplicate step ids, cycles through `needs` or branches, unknown
action ids, unknown reference namespaces, or unknown branch targets. Only
`ambrosia/v1` documents are accepted, and unknown fields are rejected.

## "Preset list is empty"

`preset list` scans the configured directories (`builtin_presets` for the CLI)
plus the writable workspace directory (`.ambrosia/presets`). Run it from the
repository root to see shipped presets, or save one with `ambrosia preset save`
to place it in your workspace.

## "I cannot save over an existing preset id"

That is intentional: ids are never silently overwritten. Choose a new id with
`--as`. This preserves reproducibility and avoids changing a preset that other
workflows may reference.

## "The dashboard does not show my new artifact yet"

The TUI dashboard re-reads artifacts on refresh. Press `r` (or use the view's
Refresh button) to recompute suggestions. The artifact itself is persisted by
the engine immediately.

## "Nmap found `microsoft-ds` but the SMB action is not suggested"

Follow-up prerequisites accept both canonical labels (`smb`) and the service
names Nmap actually emits. The accepted aliases are declared in the pack's
`actions.py`. If your scanner reports a different label, add it to the alias
list in a reviewed pack change.

## "Timeout or cancellation did not stop the tool"

Process execution uses `asyncio.create_subprocess_exec` and terminates/reaps
the child on timeout and cancellation. Verify you are running through the job
engine (CLI/TUI/preset) rather than invoking a tool directly.

## "Help output differs from the planning docs"

The planning docs describe the target design. `docs/CONTRACT_STATUS.md`
records deliberate deviations (for example, setuptools instead of Poetry). The
authoritative CLI surface is `ambrosia --help`.
