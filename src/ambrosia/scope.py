"""IP-based scope allowlist/denylist policy.

Optional, opt-in control layer (Ambrosia v2 Phase 4). The policy is disabled by
default so nothing changes unless an operator explicitly opts in. This module is
a pure data layer: it knows nothing about the TUI, CLI, executor, or session
state. Integration with those layers happens separately.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile

__all__ = [
    "ScopePolicy",
    "ScopeCheckResult",
    "check_target",
    "load_scope_policy",
    "save_scope_policy",
]

DEFAULT_SCOPE_PATH = Path.home() / ".ambrosia" / "scope.json"

_VALID_MODES = ("allowlist", "denylist")


@dataclass(frozen=True)
class ScopePolicy:
    """IP-based scope policy governing which targets may be executed.

    All fields default to "off": ``enabled`` is False so the policy is a
    no-op until an operator opts in. ``include_cidrs`` empty means "allow
    every IP" when the policy is enabled in allowlist mode.
    """

    enabled: bool = False
    include_cidrs: list[str] = field(default_factory=list)
    exclude_cidrs: list[str] = field(default_factory=list)
    mode: str = "allowlist"

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict."""
        return {
            "enabled": self.enabled,
            "include_cidrs": list(self.include_cidrs),
            "exclude_cidrs": list(self.exclude_cidrs),
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ScopePolicy:
        """Deserialize from a JSON dict, tolerating missing or bad keys."""
        enabled = bool(data.get("enabled", False))
        include_raw = data.get("include_cidrs")
        include = [str(item) for item in include_raw] if isinstance(include_raw, list) else []
        exclude_raw = data.get("exclude_cidrs")
        exclude = [str(item) for item in exclude_raw] if isinstance(exclude_raw, list) else []
        mode = str(data.get("mode", "allowlist"))
        if mode not in _VALID_MODES:
            mode = "allowlist"
        return cls(
            enabled=enabled,
            include_cidrs=include,
            exclude_cidrs=exclude,
            mode=mode,
        )


@dataclass(frozen=True)
class ScopeCheckResult:
    """Result of checking a target against a :class:`ScopePolicy`."""

    allowed: bool
    reason: str


def _ip_in_networks(
    target_ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    cidrs: list[str],
) -> bool:
    """Return True if ``target_ip`` falls inside any valid CIDR in ``cidrs``.

    Invalid CIDR strings are skipped. An address only matches a network of the
    same IP version (IPv4 never matches IPv6 and vice versa).
    """
    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if isinstance(target_ip, ipaddress.IPv4Address) and isinstance(
            network, ipaddress.IPv4Network
        ):
            if target_ip in network:
                return True
        elif isinstance(target_ip, ipaddress.IPv6Address) and isinstance(
            network, ipaddress.IPv6Network
        ):
            if target_ip in network:
                return True
    return False


def check_target(target: str, policy: ScopePolicy) -> ScopeCheckResult:
    """Check whether ``target`` is allowed by ``policy``.

    A disabled policy always allows. Otherwise ``target`` must parse as an IPv4
    or IPv6 address; allowlist mode requires a match in ``include_cidrs``
    (empty include list allows all) and no match in ``exclude_cidrs``;
    denylist mode requires no match in ``exclude_cidrs``.
    """
    if not policy.enabled:
        return ScopeCheckResult(allowed=True, reason="scope disabled")

    try:
        target_ip = ipaddress.ip_address(target)
    except ValueError:
        return ScopeCheckResult(allowed=False, reason="target is not an IP address")

    if policy.mode == "denylist":
        if _ip_in_networks(target_ip, policy.exclude_cidrs):
            return ScopeCheckResult(
                allowed=False,
                reason=f"target {target} matches an excluded CIDR",
            )
        return ScopeCheckResult(allowed=True, reason="target allowed by denylist")

    # allowlist mode (default)
    if policy.include_cidrs and not _ip_in_networks(target_ip, policy.include_cidrs):
        return ScopeCheckResult(
            allowed=False,
            reason=f"target {target} not in any included CIDR",
        )
    if _ip_in_networks(target_ip, policy.exclude_cidrs):
        return ScopeCheckResult(
            allowed=False,
            reason=f"target {target} matches an excluded CIDR",
        )
    return ScopeCheckResult(allowed=True, reason="target allowed by allowlist")


def load_scope_policy(path: Path | None = None) -> ScopePolicy:
    """Load a :class:`ScopePolicy` from ``path``.

    Defaults to ``~/.ambrosia/scope.json``. Returns a disabled policy when the
    file is missing, empty, or contains invalid JSON, so a bad config never
    blocks execution.
    """
    file_path = path if path is not None else DEFAULT_SCOPE_PATH
    if not file_path.exists():
        return ScopePolicy()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ScopePolicy()
    if not isinstance(data, dict):
        return ScopePolicy()
    return ScopePolicy.from_dict(data)


def save_scope_policy(policy: ScopePolicy, path: Path | None = None) -> None:
    """Atomically persist ``policy`` to ``path``.

    Defaults to ``~/.ambrosia/scope.json``. The payload is written to a
    temporary file in the same directory and then renamed over the target, so
    a crash mid-write never leaves a partial file. Parent directories are
    created as needed.
    """
    file_path = path if path is not None else DEFAULT_SCOPE_PATH
    file_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(policy.to_dict(), indent=2, allow_nan=False, ensure_ascii=False) + "\n"
    _atomic_write_text(file_path, text)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically via a temp file in the same dir."""
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(text)
        temp_path = Path(temp_file.name)
    try:
        temp_path.replace(path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
