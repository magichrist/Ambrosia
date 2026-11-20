# Developer guide

Authoring guides for extending Ambrosia. All extensions go through the shared
contracts in `docs/01_SHARED_CONTRACTS.md`; do not introduce parallel models.

- [Action authoring](action-authoring.md) — define an operation and its handler
- [Preset authoring](preset-authoring.md) — compose actions declaratively
- [Pack authoring](pack-authoring.md) — bundle and register actions
- [Phase authoring](phase-authoring.md) — organizational labels (no permissions)
- [Parser authoring](parser-authoring.md) — turn tool output into typed artifacts

For high-impact tool wrappers, see `docs/authorized-operations.md` and the
`authorized_operations` pack. Those actions require the authorization gate in
`policy/authorization.py` and must never be auto-registered.

Also see `docs/architecture.md`, `docs/security-model.md`,
`docs/CONTRACT_STATUS.md`, and `docs/decisions/`.

## Development workflow

```bash
python -m pip install -e ".[dev]"
pytest -q
mypy src
ruff check .
ruff format --check .
```

The release gate in `.github/workflows/ci.yml` runs those checks, builds the
wheel/sdist, and smoke-tests CLI help. Tests must not require a live target or
a real security tool; use fixtures and fake executors.

## Safety rule for contributors

Never add credential extraction/replay, password spraying, lateral movement,
unauthorized remote command execution, persistence, evasion, destructive
actions, or exfiltration to the built-in pack. New sensitive capabilities
require a separate threat model, explicit authorization design, and an ADR.
