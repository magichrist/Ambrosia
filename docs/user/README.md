# Operator guide

This guide covers the day-to-day use of Ambrosia v0.1. Commands are shown for
the CLI; the same use cases are available in the TUI (`python -m ambrosia.tui`).

## 1. Create an engagement and define scope

An engagement is a named unit of work with its own scope, targets, context,
artifacts, executions, and findings. Creating one also creates a conservative,
empty scope: **an empty scope authorizes no network action**.

```bash
ambrosia engagement create lab-windows
ambrosia engagement list
ambrosia engagement use <engagement-id>

ambrosia scope show
ambrosia scope update --engagement <engagement-id> --include-host 192.0.2.10
ambrosia scope update --engagement <engagement-id> --include-cidr 192.0.2.0/24
ambrosia scope update --engagement <engagement-id> --exclude-host 192.0.2.99
ambrosia scope update --engagement <engagement-id> --allowed-port 445
```

Scope supports includes, exclusions, allowed ports, expiry, concurrency/rate
limits, allowed effects, and approval requirements. Exclusions take precedence
over includes. In the TUI, press `g` to switch engagements and `t` for the
target/scope view.

## 2. Add a target

```bash
ambrosia target add 192.0.2.10 --engagement <engagement-id>
ambrosia target list --engagement <engagement-id>
```

In the TUI, open `t`, type a host/IP/domain into the input, and choose **Add
target**. Selecting a target in the list makes it the active context for
availability checks and execution.

## 3. Find and inspect actions

```bash
ambrosia actions list
ambrosia actions info network.nmap.service_discovery
ambrosia actions check network.nmap.service_discovery
```

Actions are never hidden: global search shows all registered actions with their
state and explanation. States are `available`, `needs_input`, `needs_approval`,
`blocked`, `missing_dependency`, and `not_applicable`. A blocked action shows the
scope or policy reason; a suggestion shows which artifact made it relevant.

The TUI dashboard (`r` to refresh) recomputes suggestions from the current
engagement and selected target.

## 4. Run an action

```bash
# A safe smoke action with no external tool
# (run via a preset, or use the TUI action details Run / Dry-run buttons)
ambrosia preset run <preset-id> --engagement <engagement-id>
```

In the TUI, open an action from the dashboard, review its metadata and
availability, optionally open **Typed inputs...**, then choose **Dry run
(preview)** for a sanitized plan or **Run**. Long jobs never freeze the UI;
use `j` (job monitor) to watch progress, inspect events, or cancel.

## 5. Presets

Presets compose actions into repeatable workflows.

```bash
ambrosia preset list
ambrosia preset validate builtin_presets/network.basic-discovery.yaml
ambrosia preset plan network.basic-discovery
ambrosia preset save builtin_presets/network.basic-discovery.yaml \
    --as network.my-discovery --name "My Discovery"
ambrosia preset run network.my-discovery --engagement <engagement-id>
```

`save` forks a validated preset into your workspace (`.ambrosia/presets`) under
a **new** id — existing ids are never overwritten. Saved presets appear in
`preset list` immediately. In the TUI press `p`, select a preset, and use
**Save a copy...**.

See `docs/presets.md` for the document format.

## 6. Export evidence

```bash
ambrosia report export --engagement <engagement-id> --format json \
    --output-file evidence.json
```

The bundle contains safe display data only: engagement, scope, targets,
artifacts, executions, and findings. Secret values are never exported; only
opaque references appear.

## 7. Jobs

```bash
ambrosia jobs list --engagement <engagement-id>
ambrosia jobs show <job-id>
ambrosia jobs cancel <job-id>
```

Every state transition is persisted. A cancelled job records its cancellation
event; an interrupted job is not silently marked successful.

## 8. Opt-in authorized operations (high impact)

For engagements that explicitly authorize credential access, remote execution,
or NTLM relay, an optional pack wraps installed Impacket/NetExec/samdump2
binaries. It is **never** enabled by default. An integrator must register it
explicitly, the scope must allow the effects, and every run requires an
authorization reference:

```bash
ambrosia preset run authorized.smb-assessment \
    --engagement <engagement-id> --authorization ROE-2026-014
```

In the TUI, fill the **Authorization reference** field in action details before
choosing **Run**. Set `show_output: true` only if you accept that raw tool output
(hashes, etc.) will be stored in execution history. See
`docs/authorized-operations.md` for the full safety case.

## Troubleshooting

See `troubleshooting.md`.
