# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Opt-in authorized operations pack** (ADR-0012, `docs/authorized-operations.md`):
  argv-based wrappers for installed Impacket `secretsdump.py`/`psexec.py`/
  `GetADUsers.py`/`ntlmrelayx.py`, NetExec (`netexec`), and `samdump2`. Never
  registered by default. No tools are installed or downloaded.
- **Layered authorization gating**: explicit pack registration, scope effect
  allowlisting, a per-run authorization reference (CLI `--authorization`, TUI
  input field), and the engine's existing approval state. High-impact handlers
  repeat the gate before building argv.
- Raw tool output is no longer persisted by default; `show_output: true` is an
  explicit opt-in documented as sensitive.

### Fixed

- The availability matcher now enforces the scope effect allowlist for actions
  with no target (offline actions), and reports disabled packs as
  `not_applicable` without unrelated findings.

## [0.1.0] — 2026-11-20

First end-to-end vertical slice. Milestones M0–M6 of `docs/03_ROADMAP_AND_ACCEPTANCE.md`
are implemented; the extension ecosystem (M7) remains postponed by design.

### Added

- **Core contracts and storage** — Pydantic domain models for engagement, scope, target, artifact, execution, observation, finding, action, preset, and phase; SQLAlchemy repositories and an initial Alembic migration; typed artifact registry with provenance, target binding, sensitivity, expiry, and supersession.
- **Context and registry** — engagement-scoped context snapshots, deterministic action-availability matcher with explainable statuses, pack manifest validation, duplicate/conflict detection.
- **Presets** — `ambrosia/v1` safe YAML loader, typed reference grammar, constrained predicates, branch (`then`/`else`) planning, deterministic dry-run, and workspace-local preset forking via `ambrosia preset save`.
- **Policy and execution** — scope validation (hosts, CIDRs, domains, exclusions, ports, expiry), effect classification, approval state model, durable job lifecycle with event stream, shell-free `asyncio.create_subprocess_exec` process executor with argv arrays, timeouts, output caps, cancellation, and secret redaction.
- **Interfaces** — Typer CLI covering engagement, scope, target, actions, preset, jobs, and report commands with stable `--output json`; adaptive Textual TUI with context rail, dashboard, search, action details, preset browser, job monitor, artifact and finding views, and typed input collection.
- **Windows assessment pack** — read-only Nmap service discovery adapter (XML parser, state normalization, `<hostscript>` support) plus SMB/LDAP/HTTP/RDP/WinRM observation actions that declare real Nmap service-name aliases; example preset and documented limitations.
- **Evidence** — JSON engagement evidence bundle export with opaque-only secret handling.
- **Quality gates** — Ruff lint and format checks, strict mypy, pytest unit/contract/TUI suites, CI workflow, developer and operator documentation, architecture decision records, and Apache-2.0 licensing.

### Notes

- The project uses setuptools with `pyproject.toml` rather than Poetry; there is no `poetry.lock`. This is a recorded deviation from the initial plan (see `docs/CONTRACT_STATUS.md`).
- Built-in actions are trusted in-process code. The JSON-RPC subprocess plugin protocol is a future (M7) capability and is not implemented.
- No credential extraction, replay, spraying, lateral movement, persistence, evasion, or exfiltration capability is included.
