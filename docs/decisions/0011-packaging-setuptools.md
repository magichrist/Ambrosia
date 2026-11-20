# ADR 0011 — setuptools build backend instead of Poetry

- Status: Accepted
- Date: 2026-11-20

## Context

The initial plan specified Poetry and a committed `poetry.lock`. The repository
was bootstrapped with `pyproject.toml` using the setuptools backend and a
`.venv` managed with pip.

## Decision

Keep setuptools as the build backend. Declare compatible dependency ranges in
`pyproject.toml`, include `build` in the dev extra, and exercise wheel/sdist
builds in CI. Commit `src/ambrosia.egg-info/` metadata because it is already
tracked. There is no `poetry.lock`.

## Consequences

- `pip install -e ".[dev]"` is the supported developer install; Poetry commands
  in the planning docs are not applicable.
- Dependency resolution is not locked; CI uses the declared ranges.
- The deviation is recorded in `docs/CONTRACT_STATUS.md` so contributors do not
  "fix" it by reintroducing Poetry without a decision.
