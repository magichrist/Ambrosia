# Ambrosia — First Sprint Backlog

This backlog converts the roadmap into small builder-ready tasks. The lead may map these IDs into GitHub Issues, Linear, or another tracker.

## Sprint objective

Produce a clean Python package with frozen contracts and a minimal executable shell. Do not build the full workflow engine in this sprint.

## P0 — Required

### AMB-001 — Inspect repository and record baseline

**Owner:** Lead  
**Tasks:** inspect tree, Git status, Python version, Poetry presence, tests, docs.  
**Acceptance:** baseline report committed; existing user files preserved.

### AMB-002 — Create Poetry project and `src/` package

**Owner:** Lead  
**Tasks:** configure Python 3.12+, package metadata, `ambrosia` console script, `python -m ambrosia`, test and lint tools.  
**Acceptance:** clean install and CLI help work.

### AMB-003 — Add shared error hierarchy

**Owner:** Lead / Agent 1  
**Tasks:** stable exception codes and safe messages.  
**Acceptance:** tests confirm error serialization contains no sensitive values.

### AMB-004 — Implement engagement, target, and scope contracts

**Owner:** Agent 1  
**Tasks:** Pydantic models, validators, scope defaults, ID conventions.  
**Acceptance:** invalid targets and empty/unbounded scope are rejected as designed.

### AMB-005 — Implement Artifact base contract

**Owner:** Agent 1  
**Tasks:** artifact base model, type registry interface, provenance, sensitivity, secret reference.  
**Acceptance:** no raw secret values can be represented in a persisted artifact.

### AMB-006 — Implement SQLite repositories

**Owner:** Agent 2  
**Tasks:** initial SQLAlchemy models and repositories.  
**Acceptance:** create/read/list tests pass with temporary DB.

### AMB-007 — Establish architecture decision records

**Owner:** Lead  
**Tasks:** record modular monolith, context vs phase, action/preset boundary, safe executor, plugin trust boundary.  
**Acceptance:** ADRs linked from architecture docs.

## P1 — Required for first vertical slice

### AMB-008 — Define ActionDefinition and ActionHandler contracts

**Owner:** Lead / Agent 3  
**Acceptance:** a test action can be registered with typed input/output metadata.

### AMB-009 — Implement registry load/list/info/search

**Owner:** Agent 3  
**Acceptance:** fixture pack loads; duplicates and invalid definitions produce clear errors.

### AMB-010 — Implement ActionAvailability matcher

**Owner:** Agent 3  
**Acceptance:** a required `network.service` artifact makes a test action available for the same target; absent/wrong-target artifact does not.

### AMB-011 — Implement context snapshot and artifact query service

**Owner:** Agent 1  
**Acceptance:** service returns target-aware context using repository protocols.

### AMB-012 — Implement basic phase definition schema

**Owner:** Agent 4  
**Acceptance:** user-defined phases can group actions/presets but cannot grant execution permission.

### AMB-013 — Add fake executor and execution events

**Owner:** Agent 5  
**Acceptance:** fake execution emits progress, result, and artifact events without network access.

## P2 — After the first vertical slice starts passing

### AMB-014 — Implement preset YAML loader and validator

**Owner:** Agent 4

### AMB-015 — Implement typed variable reference parser

**Owner:** Agent 4

### AMB-016 — Implement dry-run plan generator

**Owner:** Agent 4 / Agent 5

### AMB-017 — Implement policy scope validator

**Owner:** Agent 5

### AMB-018 — Implement safe process executor

**Owner:** Agent 5

### AMB-019 — Build adaptive Textual workspace shell

**Owner:** Agent 6

### AMB-020 — Add Typer engagement/action/preset command groups

**Owner:** Agent 7

### AMB-021 — Build fixture-backed end-to-end flow

**Owner:** Agent 9

## Sprint review checklist

- [ ] The repo installs cleanly.
- [ ] Contracts are frozen and documented.
- [ ] A test engagement can be created and persisted.
- [ ] An artifact can be created and persisted.
- [ ] An action can be registered and searched.
- [ ] Availability is computed from context and target provenance.
- [ ] A fake execution produces an artifact and an execution record.
- [ ] Full tests, lint, and type checks pass.
- [ ] All agents submitted handoff reports.
- [ ] Lead documented remaining blockers and next sprint.
