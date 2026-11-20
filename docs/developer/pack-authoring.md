# Pack authoring

A pack bundles action definitions, handlers, parsers, presets, and docs for a
domain. `src/ambrosia/packs/windows_assessment/` is the reference.

## Layout

```
src/ambrosia/packs/<pack_name>/
├── __init__.py      # PACK_MANIFEST, load_manifest(), register_pack()
├── actions.py       # ActionDefinition instances (metadata only)
├── handlers.py      # ActionHandler implementations
├── docs/            # actions.md, limitations.md
└── examples/        # example presets
```

## Registration contract

```python
def register_pack(registry: Registry, *, executor: ActionHandler | None = None) -> LoadResult:
    manifest = load_manifest()
    for action in manifest.actions:
        registry.register(action, handler=make_handler(action.id, executor),
                          pack_id=manifest.metadata.id, source="pack")
    ...
```

- `load_manifest()` validates `PackManifest` and returns it without side effects.
- `register_pack()` must never execute a tool or run an assessment. Tool
  availability is metadata (a PATH check) evaluated by the matcher.
- An injected executor (typically `FakeExecutor` in tests) lets the whole pack
  run without the real tool installed.
- Duplicate action ids and invalid definitions are rejected by the registry.

## Manifest

`api_version: ambrosia/v1`, `kind: pack`, `metadata` with `id`, `name`,
`version`, `description`, and an `actions` list of serialized `ActionDefinition`
objects. Derive the action list from the same Python definitions used by
handlers so there is one source of truth.

## Service-name aliases

If your tool reports vendor-specific labels (Nmap reports `microsoft-ds`,
`ms-wbt-server`, `wsman`), declare accepted aliases in the action's artifact
requirements. The matcher treats a collection in a `where` predicate as
"any of these values" so real scans and canonical labels both work.

## Safety and docs

- Declare effects honestly; the initial pack uses only `network_observe` and
  `local_read`.
- Document limitations explicitly (observations are not proof of exploitability).
- Never include credential access, replay, spraying, lateral movement,
  persistence, evasion, or exfiltration in a built-in pack.

## Tests

Pack loads and validates; metadata declares effects, target fields, and
dependencies; parsers handle good and malformed fixtures; artifacts change
suggestions; modules refuse out-of-scope targets; dry-run works with no tool.
