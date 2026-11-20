# Parser authoring

Parsers turn machine-readable tool output into typed artifacts. The reference
implementation is `src/ambrosia/executors/adapters/nmap.py` plus
`executors/adapters/base.py`.

## Principles

- Prefer structured output (Nmap XML via `-oX -`) over human-readable tables.
- Keep the tool adapter (argv building + parsing) separate from the action
  handler (event stream) where practical.
- Validate inputs at runtime: the adapter contract accepts generic `object`
  values, so reject invalid values before producing argv.
- Build bounded argv arrays with no shell. The Nmap adapter uses `-Pn`, `-sV`,
  an explicit port list, and a single target.
- Parse defensively: malformed or partial XML should yield a bounded result or
  a structured error, never an unhandled crash.
- Normalize tool-specific states (for example Nmap `open|filtered`) into a
  canonical state field; capture `<hostscript>` output as an observation.

## Producing artifacts

Handlers emit `ArtifactProducedEvent` with typed drafts. Use the artifact
creation helpers in `ambrosia.artifacts.lifecycle` and the registered artifact
schemas in `ambrosia.artifacts.models`. Always set:

- `engagement_id`, `type`, validated `value`
- `source` and `source_execution_id`
- `target_ref` (so target-bound prerequisites work)
- `sensitivity`, and `secret_ref` instead of raw secrets when relevant

## Service-name aliases

Real scanners report vendor labels (`microsoft-ds`, `ms-wbt-server`, `wsman`).
Declare aliases in the consuming actions' `ArtifactRequirement.where` clauses
rather than rewriting values in the parser, so provenance stays faithful to the
tool output. The matcher's any-of semantics handle the mapping.

## Tests

- expected and malformed fixtures
- argv is bounded and shell-free, with separate argument values
- state normalization and host-script observations
- produced artifacts carry target provenance and correct sensitivity
- resulting artifacts change the availability of follow-up actions
- dry-run and fixture-backed runs need no real tool
