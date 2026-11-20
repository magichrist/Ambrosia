# Ambrosia

**Context-driven automation workbench for authorized security assessment and policy-governed automation.**

Ambrosia is a modular Python application that turns operator knowledge, tools, and scripts into reusable, typed, context-aware actions and presets. It is not a fixed pentest checklist: the current engagement context determines which actions are relevant and usable, and the interface adapts as artifacts are discovered.

The first domain pack is a **read-only Windows assessment pack** (Nmap service discovery plus SMB/LDAP/HTTP/RDP/WinRM observation). The core is domain-neutral.

> **Status — v0.1:** the end-to-end vertical slice is implemented and tested. Milestones M0–M6 are complete; the extension/plugin ecosystem (M7) is deliberately postponed. See [Known limitations](#known-limitations) and `docs/CONTRACT_STATUS.md`.

An **opt-in** authorized-operations pack is also available for engagements that
explicitly permit high-impact testing. It wraps installed Impacket, NetExec,
and samdump2 binaries through the shell-free argv executor and is never enabled
by default. See `docs/authorized-operations.md`.

---

## Safety boundary

Ambrosia is built for **authorized** assessment and general automation. The default built-in pack performs bounded discovery and read-only configuration observation only. It deliberately does **not** include credential dumping or replay, hash-based remote access, password spraying, lateral movement, unauthorized remote command execution, persistence, stealth/evasion, destructive actions, or exfiltration. Secrets are represented as opaque references, never as plaintext values in YAML, the database, logs, previews, or reports.

A separate, **opt-in** `authorized-operations` pack (ADR-0012) wraps 46 installed
Windows/AD assessment tools covering RDP, identity/user extraction, vulnerability
scans, Windows spec/details, network/protocol, credentials, Kerberos, and lateral
movement. It is never registered by default. Actions are classified by declared
effects: read-only probes run under scope policy, while high-impact actions
require explicit registration, scope effect allowlisting, a per-run authorization
reference, and engine approval. See `docs/authorized-operations.md` and the
[coverage matrix](src/ambrosia/packs/authorized_operations/docs/coverage.md).

You must define an explicit scope before any network action is available. Policy and scope are checked again immediately before execution on every path (CLI, TUI, and presets).

---

## Requirements and installation

Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Verify the setup:

```bash
ambrosia --help
python -m ambrosia --help
pytest -q
mypy src
ruff check .
ruff format --check .
```

---

## Command-line quickstart

```bash
# Create an engagement (a conservative, empty scope is created with it)
ambrosia engagement create lab-windows
ambrosia engagement list
ambrosia engagement use <engagement-id>

# Define the authorized boundary and add a target
ambrosia scope update --engagement <engagement-id> --include-host 192.0.2.10
ambrosia target add 192.0.2.10 --engagement <engagement-id>

# Discover what is available and why
ambrosia actions list
ambrosia actions info network.nmap.service_discovery
ambrosia actions check network.nmap.service_discovery

# Presets: validate, preview, run, and save as reusable workflows
ambrosia preset list
ambrosia preset validate builtin_presets/network.basic-discovery.yaml
ambrosia preset plan network.basic-discovery
ambrosia preset save builtin_presets/network.basic-discovery.yaml --as network.my-discovery
ambrosia preset run network.basic-discovery --engagement <engagement-id>

# Inspect and export
ambrosia jobs list
ambrosia jobs show <job-id>
ambrosia jobs cancel <job-id>
ambrosia report export --engagement <engagement-id> --format json
```

Add `--output json` to any command for stable, script-friendly JSON.

## Textual interface

```bash
python -m ambrosia.tui
```

The workspace keeps a stable frame (status bar, context rail, main content, activity panel) while the main content changes with context: engagements, dashboard, target/scope, presets, jobs, artifacts, findings, and action details.

| Key | Action |
|---|---|
| `/` | global search / command palette |
| `Tab` | move between regions |
| `Enter` | open / select |
| `Esc` | back / close modal |
| `g` | engagement switcher |
| `r` | refresh suggestions |
| `t` | target / scope |
| `p` | preset browser |
| `j` | job monitor |
| `f` | findings |
| `a` | artifact browser |
| `?` | help |
| `q` | quit (confirms when jobs are active) |

The TUI launches with in-memory fakes so it works without a configured database. It calls the same application services as the CLI.

---

## How it works

1. An **engagement** owns a scope, targets, context, artifacts, executions, and findings.
2. A **scope** is the explicit authorization boundary; empty means nothing is authorized.
3. **Actions** declare typed inputs, required artifacts, effects, dependencies, and scope fields.
4. The pure **matcher** explains why each action is available, needs input, needs approval, is blocked, missing a dependency, or not applicable.
5. The **job engine** validates policy, runs the action through a shell-free argv executor, streams events, and parses machine-readable output.
6. Parsers emit typed **artifacts** with provenance; the context matcher then surfaces newly relevant actions.
7. **Presets** compose actions declaratively; a dry-run resolves a deterministic plan without launching any process.

Documentation:

- `docs/architecture.md` — packages, dependency direction, data flow
- `docs/security-model.md` — scope, effects, approvals, executor, secrets
- `docs/authorized-operations.md` — safety case for the opt-in high-impact pack
- `docs/presets.md` — preset schema, references, branches, saving
- `docs/CONTRACT_STATUS.md` — frozen contracts and deliberate deviations
- `docs/user/` — operator guide
- `docs/developer/` — authoring guides
- `docs/decisions/` — architecture decision records

---

## Verification

The release gate (also encoded in `.github/workflows/ci.yml`) is:

```bash
ruff check . && ruff format --check . && mypy src
pytest -q
python -m build
ambrosia --help && python -m ambrosia --help
```

Tests use fixtures and fake executors; no live target or Nmap installation is required.

## Known limitations

- The artifact-to-suggestion chain is persisted by the engine, but the TUI dashboard re-reads artifacts on its next refresh rather than receiving a live event push.
- LDAP domain identification is a documented hostname heuristic, not an authoritative directory query.
- The Nmap service aliases accepted by follow-up actions are declared explicitly in the pack; new scanner labels need to be added there.
- `preset plan` produces a simplified `needs`-only step view; condition branch gating is applied by the full `PresetLoader` at execution time.
- The third-party plugin protocol (M7) is specified but not implemented; only trusted built-in Python packs are supported today.
- `src/ambrosia.egg-info/` is tracked in git and regenerated on build.

## License

Apache License 2.0 — see `LICENSE`.
