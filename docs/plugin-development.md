# Extension development

## Current status (v0.1)

Ambrosia supports **trusted, in-process built-in packs** written in Python. A
third-party plugin isolation protocol is designed but **not implemented**
(milestone M7 is postponed). There is no pack marketplace, remote installer, or
dynamic loading of arbitrary Python from user folders.

## Adding a built-in pack today

A pack is a Python package under `src/ambrosia/packs/` that:

1. Declares an immutable `PackManifest` with `api_version: ambrosia/v1`,
   metadata (`id`, `name`, `version`), and action definitions.
2. Provides a `register_pack(registry, *, executor=None) -> LoadResult` function
   that validates the manifest and registers each `ActionDefinition` with its
   handler. Registration must be metadata-only — never execute a tool or
   run an assessment.
3. Declares tool availability as metadata (`ToolDependency.check_command`);
   actual PATH checks are performed by the availability matcher, not at import.
4. Exposes handlers implementing `ActionHandler.execute(request, context)` as
   an async generator of `ExecutionEvent` variants.

See `src/ambrosia/packs/windows_assessment/__init__.py` for the reference
implementation and `docs/developer/pack-authoring.md` for a walkthrough.

Built-in code is trusted: it runs in the main process. Do not load untrusted
Python entry points as if they were sandboxed.

## Future third-party plugin protocol (M7, not implemented)

The designed boundary is a versioned **JSON-RPC 2.0 over stdio** subprocess
protocol:

- Each plugin is a separate process with a versioned capability declaration.
- The host launches the plugin with a fixed, allowlisted executable; plugin
  discovery never implies trust.
- Every plugin request passes through the same policy, scope, and approval
  gates as built-in actions.
- Plugin outputs are schema-validated into domain artifacts before entering
  context.
- A plugin crash or protocol violation cannot crash the core process; it is
  reported as a structured failure for that execution.
- Plugin metadata includes compatibility ranges, declared effects, and trust
  / review status.

Until this protocol and its compatibility/trust model exist, external
functionality should be added as a reviewed, versioned built-in pack in a
fork rather than loaded dynamically.
