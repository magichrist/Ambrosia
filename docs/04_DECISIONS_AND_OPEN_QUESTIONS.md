# Ambrosia — Architecture Decisions and Open Questions

This document captures decisions that should be treated as settled for the first implementation unless the lead records a change in an ADR.

## 1. Decisions to freeze for v0.1

### D-001: Modular monolith

**Decision:** Build one Python application with strongly separated packages.  
**Reason:** Easier local installation, testing, and debugging; no need for a distributed control plane in the first release.

### D-002: Context is not a phase

**Decision:** The context engine determines applicability. Phases are user-owned groups/views.  
**Reason:** The operator's journey is dynamic and non-linear.

### D-003: Artifacts are immutable and typed

**Decision:** Store immutable artifact records with provenance; represent changes with superseding artifacts.  
**Reason:** Reproducibility, evidence integrity, and safer variable resolution.

### D-004: Actions are the smallest unit

**Decision:** One action does one well-described operation. Presets compose actions.  
**Reason:** Reuse and predictable testing.

### D-005: Presets are declarative YAML

**Decision:** Presets are validated data, not executable Python.  
**Reason:** Easy authoring, diffing, review, and validation.

### D-006: Strict typed references

**Decision:** No arbitrary Jinja/Python expression evaluation.  
**Reason:** Prevent code execution hidden inside a preset and make data-flow validation possible.

### D-007: Process execution is argv-based

**Decision:** Use `asyncio.create_subprocess_exec`; never build shell strings from preset input.  
**Reason:** Avoid shell injection and improve cross-platform behavior.

### D-008: Textual + Typer share services

**Decision:** All business behavior lives in application services.  
**Reason:** TUI, CLI, future API, and automation all behave consistently.

### D-009: SQLAlchemy synchronous repositories at first

**Decision:** Use short synchronous repository transactions; run potentially blocking work in worker threads where needed.  
**Reason:** Keep initial SQLite persistence simple. Revisit only with measured need.

### D-010: Extension trust boundary

**Decision:** Built-in actions can run in-process. Future third-party extensions should communicate over a versioned JSON-RPC subprocess protocol. Python entry points may identify trusted installed extensions but do not make them sandboxed.  
**Reason:** Loading arbitrary plugin code into the main process is not isolation.

### D-011: General-purpose core, Windows-first pack

**Decision:** Core models and engines are domain-neutral. Windows/AD is a pack.  
**Reason:** Preserve the possibility of automation beyond red teaming without rewriting the core.

### D-012: Safe read-only first pack

**Decision:** Initial built-in Windows pack focuses on discovery and configuration assessment; no credential theft/replay, remote command execution, persistence, stealth, or exfiltration.  
**Reason:** Keep the first release testable, auditable, and safe by default.

## 2. Open questions for the lead (resolve before M2)

1. **Workspace layout:** Should Ambrosia support one workspace directory per engagement, or one workspace containing many engagements? Recommendation: one workspace with multiple engagements; provide export/import bundles.
2. **Phase storage:** Workspace-level reusable phases, engagement-local phases, or both? Recommendation: built-in/workspace phases with optional engagement overrides.
3. **User preset precedence:** Built-in pack preset, workspace preset, and engagement override order? Recommendation: never silently override IDs; use explicit copy/fork and version pinning.
4. **Secrets provider:** `keyring` integration initially, or defer actual secret storage and only define a protocol? Recommendation: define the protocol in M1, add OS provider only after testing on supported platforms.
5. **External plugin protocol:** JSON-RPC over stdio, newline-delimited JSON, or another transport? Recommendation: JSON-RPC 2.0 over stdio with versioned schemas.
6. **Action installation:** Local directory packs first, Python entry-point packages later? Recommendation: local built-in packs for v0.1; entry points or remote plugin installers after trust/compatibility model exists.
7. **Target identity:** How are hostname, resolved IP, aliases, and multiple interfaces represented? Recommendation: stable Asset ID plus endpoint artifacts, retaining resolution timestamps and sources.
8. **Context event model:** Persist every event or only execution/artifact events? Recommendation: persist all meaningful state transitions, but avoid noisy UI-only events.
9. **Output retention:** What is the default retention for raw tool output? Recommendation: retain in evidence store with configurable size caps; redact known secrets before persistence.
10. **Preset authoring UX:** Edit YAML only in v0.1 or provide a form-based editor? Recommendation: YAML authoring plus TUI validation/preview; form editor later.

## 3. Features explicitly postponed

- Distributed workers and remote Ambrosia server.
- Browser/web UI.
- Agent installation on Windows targets.
- Arbitrary loops and full workflow programming language.
- Visual graph editor.
- Marketplace or remote pack registry.
- Automatic exploit chaining.
- Credential dumping, hash replay, password spraying, persistence, stealth/evasion, or exfiltration modules.
- AI autonomous action selection.

The architecture must not accidentally make these prerequisites for the initial product.

## 4. Future compatibility requirements

Even though these are postponed, avoid choices that make them impossible:

- Use stable action and artifact IDs.
- Version manifests and schemas.
- Keep event payloads serializable.
- Do not leak UI-specific types into the core.
- Store provenance and execution records.
- Keep execution adapters behind protocols.
- Treat context as engagement-scoped and serializable.
- Avoid arbitrary Python object persistence.
