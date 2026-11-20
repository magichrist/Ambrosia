# Architecture decision records

These ADRs capture decisions that are settled for v0.1. They supplement the
higher-level decision list in `docs/04_DECISIONS_AND_OPEN_QUESTIONS.md`.

| ADR | Decision |
|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith for v0.x |
| [0002](0002-context-not-phase.md) | Context determines applicability; phases organize views |
| [0003](0003-typed-immutable-artifacts.md) | Typed, immutable artifacts with provenance |
| [0004](0004-actions-presets.md) | Actions are the smallest unit; presets compose them |
| [0005](0005-declarative-presets-strict-references.md) | Declarative presets and strict typed references |
| [0006](0006-trust-boundary.md) | Trusted in-process built-ins; process-isolated future plugins |
| [0007](0007-safe-execution.md) | Shell-free argv execution and runtime scope checks |
| [0008](0008-interfaces-share-services.md) | Textual and Typer share application services |
| [0009](0009-synchronous-repositories.md) | Synchronous SQLAlchemy repositories at first |
| [0010](0010-windows-first-read-only-pack.md) | Domain-neutral core, read-only Windows-first pack |
| [0011](0011-packaging-setuptools.md) | setuptools build backend instead of Poetry |
| [0012](0012-authorized-operations-pack.md) | Opt-in high-impact operations pack with layered authorization gates |

New cross-cutting decisions require a new numbered ADR and an update to
`docs/CONTRACT_STATUS.md`.
