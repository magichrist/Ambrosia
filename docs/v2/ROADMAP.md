# Ambrosia v2 — Reconstruction Roadmap

This document plans the reconstruction of Ambrosia from the v1 modular monolith into the v2 TUI command launcher.

## Guiding principle

Build the smallest thing that lets an operator register a command, search it, and run it with remembered inputs — in a single TUI. Add nothing until that core loop is fast and reliable.

## Phase 1 — Core loop (MVP)

1. **Command model in Python**: `Command` and `CommandInput` dataclasses, loaded from a JSON file.
2. **Shell executor**: `create_subprocess_exec`, `{{var}}` substitution, argv building, live streaming, cancellation.
3. **Session state**: in-memory `command_id -> inputs` dict, optional JSON persistence.
4. **Textual TUI**: search bar (substring + regex), results list, preview panel, input form modal, execution view with live output.
5. **Command registration**: TUI modal to add/edit commands and save to JSON.

Exit criteria: operator can add `crackmapexec smb {{ip}}`, search `smb`, run it with an IP, see live output, and have the IP remembered for next time.

## Phase 2 — Polish

- Fuzzy/regex search refinements, debounce, invalid-regex inline errors.
- Keyboard-driven flow (no mouse required).
- Exit codes, duration, and "run again" after completion.
- Session persistence to disk (load on start, save on exit).
- Command import/export (JSON).

## Phase 3 — Ergonomics

- Command categories / favorites / pinned commands.
- Recent commands list.
- Input validation hints (e.g. "must be an IP") — soft validation, not blocking.
- Multiple sessions / named session files.

## Phase 4 — Optional controls (opt-in, not default)

- Scope allowlist (simple include/exclude IP/CIDR list) — only if the operator opts in.
- Authorization-reference field per command run — only if the operator opts in.
- Execution history log (local file) — opt-in.

These remain **off by default** and are not required for the core loop.

## Non-goals (explicitly deferred or dropped)

- No v1 application-service / repository layer.
- No v1 preset YAML DSL.
- No `Engagement / Scope / Target / Artifact / Finding` domain model.
- No Typer CLI command groups as the primary interface.
- No policy engine, effect classes, or approval state machine by default.
- No distributed server, web UI, or agent-on-target.

## Success metric

An operator can go from "I want to run `crackmapexec smb 10.0.0.5`" to seeing output in under 10 seconds, with zero CLI commands to memorize.
