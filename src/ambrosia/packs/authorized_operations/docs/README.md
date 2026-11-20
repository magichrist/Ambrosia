# Authorized operations pack

Opt-in wrappers for installed Impacket, NetExec, and samdump2 binaries. This
pack is **not** registered by default. See the full safety case at
`docs/authorized-operations.md` in the repository root.

## Enabling

```python
from ambrosia.packs.authorized_operations import register_authorized_operations

register_authorized_operations(registry)
```

Then, for the engagement:

1. widen the scope's `allowed_effects` to include the effects the action
   declares (for example `credential_access`, `authentication`,
   `remote_change`);
2. supply a per-run authorization reference;
3. grant approval when the engine requests it.

No tool is installed by this pack. The binaries must already be on PATH on the
machine performing the assessment.

- [Actions](actions.md)
- [Limitations](limitations.md)
