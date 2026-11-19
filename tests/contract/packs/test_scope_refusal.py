# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Contract tests: network actions refuse targets outside the authorized scope.

Uses the policy scope checker, the policy engine, and the availability matcher
with static scope definitions; no live target or Nmap installation is required.
"""

from __future__ import annotations

import sys

from ambrosia.artifacts.lifecycle import create_artifact
from ambrosia.domain.models import Scope
from ambrosia.packs.windows_assessment import register_pack
from ambrosia.policy.engine import PolicyEngine
from ambrosia.policy.scope import ScopeChecker
from ambrosia.registry import AvailabilityMatcher, PolicySnapshot, Registry
from ambrosia.registry.models import ContextSnapshot

_PLATFORM_MAP = {"darwin": "darwin", "linux": "linux", "win32": "windows"}


def _platform() -> str:
    return _PLATFORM_MAP.get(sys.platform, sys.platform)


def _registry() -> Registry:
    registry = Registry()
    register_pack(registry)
    return registry


def _scope() -> Scope:
    return Scope(
        engagement_id="eng-1",
        include_hosts=["10.0.0.10"],
        allowed_effects={"local_read", "network_observe"},
        require_approval_for={"local_write", "remote_change", "authentication"},
    )


def _policy() -> PolicySnapshot:
    return PolicySnapshot(
        allowed_effects=frozenset({"local_read", "network_observe"}),
        require_approval_for=frozenset(
            {"local_write", "remote_change", "authentication", "credential_access"}
        ),
        include_hosts=("10.0.0.10",),
    )


def _smb_artifact() -> object:
    """A discovered SMB service on the in-scope target."""
    return create_artifact(
        engagement_id="eng-1",
        type="network.service",
        value={
            "host_ref": "10.0.0.10",
            "port": 445,
            "protocol": "tcp",
            "service_name": "smb",
            "product": "Samba",
            "version": "4.6.2",
            "state": "open",
        },
        target_ref="10.0.0.10",
        source_id="network.nmap.service_discovery",
    )


def _context(address: str, artifacts: tuple = ()) -> ContextSnapshot:
    return ContextSnapshot(
        engagement_id="eng-1",
        selected_target={"address": address},
        artifacts=tuple(artifacts),
        inputs={"target": address},
        available_tools=frozenset({"nmap"}),
        platform=_platform(),
    )


def test_scope_checker_refuses_out_of_scope_target() -> None:
    checker = ScopeChecker()
    scope = _scope()

    in_scope = checker.is_address_in_scope("10.0.0.10", scope)
    assert in_scope.in_scope is True

    out_of_scope = checker.is_address_in_scope("99.99.99.99", scope)
    assert out_of_scope.in_scope is False
    assert out_of_scope.reason is not None


def test_policy_engine_blocks_out_of_scope_execution() -> None:
    engine = PolicyEngine()
    scope = _scope()
    registry = _registry()
    action = registry.get("windows.smb.configuration_audit")
    assert action is not None

    outcome, decision, _record = engine.evaluate(
        action=action,
        scope=scope,
        address="99.99.99.99",
        execution_id="exec-1",
        engagement_id="eng-1",
    )
    assert outcome == "blocked"
    assert decision.scope_in_scope is False

    outcome, decision, _record = engine.evaluate(
        action=action,
        scope=scope,
        address="10.0.0.10",
        execution_id="exec-2",
        engagement_id="eng-1",
    )
    assert outcome == "allowed"


def test_matcher_blocks_out_of_scope_target() -> None:
    registry = _registry()
    matcher = AvailabilityMatcher(registry)
    smb = _smb_artifact()

    # Same target, in scope, artifact present -> action available.
    in_scope = matcher.evaluate(
        "windows.smb.configuration_audit",
        _context("10.0.0.10", artifacts=(smb,)),
        _policy(),
    )
    assert in_scope.status == "available", in_scope.reasons

    # Identical artifact, but target outside scope -> blocked.
    out_of_scope = matcher.evaluate(
        "windows.smb.configuration_audit",
        _context("99.99.99.99", artifacts=(smb,)),
        _policy(),
    )
    assert out_of_scope.status == "blocked"
    assert any("blocked by scope" in r for r in out_of_scope.reasons)


def test_all_network_actions_declare_target_scope_field() -> None:
    registry = _registry()
    for action_id in (
        "network.nmap.service_discovery",
        "windows.smb.configuration_audit",
        "windows.ldap.domain_inventory",
        "windows.http.method_observation",
        "windows.rdp.exposure_observation",
        "windows.winrm.exposure_observation",
    ):
        action = registry.get(action_id)
        assert action is not None
        assert "target" in action.scope_fields
