# Limitations

- **Tools must be installed by the operator.** Ambrosia never installs or
  downloads binaries. Registration performs metadata validation only.
- **Version drift.** Tool flags change between releases. `extra_args` exists to
  accommodate this, but actions are validated against the argv builder in this
  pack; review tool versions before an engagement.
- **Authorization is an assertion.** Ambrosia records and enforces an explicit
  authorization reference but cannot verify that the operator actually holds
  authorization.
- **Output sensitivity.** Raw output may contain hashes and other credential
  material. It is not persisted by default; `show_output: true` is an explicit
  opt-in that persists output in execution events.
- **NTLM relay logistics.** The pack invokes the relay tool against the
  in-scope SMB target; it does not manage listeners, capture sources, or network
  positioning.
- **No stealth or evasion.** These wrappers make no attempt to avoid detection.
- **No automatic retries.** Failures are reported as structured events.
- **Platform.** The wrapper itself is cross-platform, but the wrapped tools may
  only be available on specific assessment distributions.
