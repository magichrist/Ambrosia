# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.
"""Contract tests for ActionAvailability: every status with explanatory reasons.

These tests lock in the matcher contract: for a fixed registry + context +
policy snapshot, the matcher explains why an action is suggested or unavailable,
and the same snapshot always yields the same result.
"""

from __future__ import annotations

from ambrosia.domain.models import Artifact
from ambrosia.registry import (
    AvailabilityMatcher,
    ContextSnapshot,
    PolicySnapshot,
    Registry,
)

PACK_TEXT = """
api_version: ambrosia/v1
kind: pack
metadata:
  id: contract-pack
  name: Contract Pack
  version: 1.0.0
  description: contract fixture pack
actions:
  - id: contract.available
    version: 1.0.0
    name: Available
    description: no requirements
    category: discovery
    tags: []
    platforms: []
    input_schema: {type: object, properties: {}, required: []}
    executor: {kind: native}
    effects: [local_read]
    risk: info
    scope_fields: []
    approval_required: false
  - id: contract.needs_input
    version: 1.0.0
    name: Needs Input
    description: requires target input
    category: discovery
    tags: []
    platforms: []
    input_schema:
      type: object
      properties:
        target: {type: string}
      required: [target]
    executor: {kind: native}
    effects: [local_read]
    risk: info
    scope_fields: [target]
    approval_required: false
  - id: contract.blocked
    version: 1.0.0
    name: Blocked
    description: effect not allowed
    category: discovery
    tags: []
    platforms: []
    input_schema: {type: object, properties: {}, required: []}
    executor: {kind: native}
    effects: [credential_access]
    risk: high
    scope_fields: []
    approval_required: false
  - id: contract.needs_approval
    version: 1.0.0
    name: Needs Approval
    description: local_write requires approval
    category: inventory
    tags: []
    platforms: []
    input_schema: {type: object, properties: {}, required: []}
    executor: {kind: native}
    effects: [local_write]
    risk: moderate
    scope_fields: []
    approval_required: true
  - id: contract.missing_dependency
    version: 1.0.0
    name: Missing Dependency
    description: requires missing tool
    category: discovery
    tags: []
    platforms: []
    input_schema: {type: object, properties: {}, required: []}
    executor: {kind: process, executable: absent-tool}
    dependencies: [{name: absent-tool}]
    effects: [local_read]
    risk: info
    scope_fields: []
    approval_required: false
  - id: contract.not_applicable
    version: 1.0.0
    name: Not Applicable
    description: requires artifact
    category: discovery
    tags: []
    platforms: []
    input_schema: {type: object, properties: {}, required: []}
    executor: {kind: native}
    effects: [local_read]
    risk: info
    required_artifacts: [{type: network.host, same_target: true}]
    scope_fields: []
    approval_required: false
"""


def _registry():
    registry = Registry()
    import yaml

    registry.load_pack(yaml.safe_load(PACK_TEXT))
    return registry


def _context(
    selected_target=None, artifacts=(), inputs=None, available_tools=(), platform="current"
):
    return ContextSnapshot(
        engagement_id="e1",
        selected_target=selected_target,
        artifacts=tuple(artifacts),
        inputs=dict(inputs or {}),
        available_tools=frozenset(available_tools),
        platform=platform,
    )


def _policy():
    return PolicySnapshot(
        allowed_effects=frozenset(["local_read", "network_observe", "local_write"]),
        require_approval_for=frozenset(["local_write", "remote_change", "authentication"]),
        include_hosts=("10.0.0.1",),
        include_cidrs=(),
        include_domains=(),
        exclude_hosts=(),
        exclude_cidrs=(),
    )


def _artifact(artifact_id, type_, target_ref, value=None):
    return Artifact(
        id=artifact_id,
        engagement_id="e1",
        type=type_,
        target_ref=target_ref,
        value=dict(value or {}),
    )


def test_each_status_has_explanatory_reasons() -> None:
    registry = _registry()
    matcher = AvailabilityMatcher(registry)
    policy = _policy()

    cases = [
        ("contract.available", _context(selected_target={"address": "10.0.0.1"}), "available"),
        (
            "contract.needs_input",
            _context(selected_target={"address": "10.0.0.1"}, inputs={}),
            "needs_input",
        ),
        (
            "contract.blocked",
            _context(selected_target={"address": "10.0.0.1"}),
            "blocked",
        ),
        (
            "contract.needs_approval",
            _context(selected_target={"address": "10.0.0.1"}),
            "needs_approval",
        ),
        (
            "contract.missing_dependency",
            _context(selected_target={"address": "10.0.0.1"}),
            "missing_dependency",
        ),
        (
            "contract.not_applicable",
            _context(selected_target={"address": "10.0.0.1"}, artifacts=()),
            "not_applicable",
        ),
    ]
    for action_id, context, expected_status in cases:
        avail = matcher.evaluate(action_id, context, policy)
        assert avail.status == expected_status, f"{action_id}: {avail.status} != {expected_status}"
        # Every non-available status must explain why.
        if expected_status != "available":
            assert avail.reasons, f"{action_id}: no reasons for {expected_status}"


def test_not_applicable_becomes_available_when_artifact_present() -> None:
    registry = _registry()
    matcher = AvailabilityMatcher(registry)
    policy = _policy()
    artifact = _artifact(
        "art-h1", "network.host", target_ref="10.0.0.1", value={"address": "10.0.0.1"}
    )
    context = _context(selected_target={"address": "10.0.0.1"}, artifacts=(artifact,))
    avail = matcher.evaluate("contract.not_applicable", context, policy)
    assert avail.status == "available"
    assert "art-h1" in avail.matched_artifact_ids


def test_target_scoped_artifact_requires_same_target() -> None:
    registry = _registry()
    matcher = AvailabilityMatcher(registry)
    policy = _policy()
    artifact = _artifact(
        "art-h2", "network.host", target_ref="10.0.0.2", value={"address": "10.0.0.2"}
    )
    context = _context(selected_target={"address": "10.0.0.1"}, artifacts=(artifact,))
    avail = matcher.evaluate("contract.not_applicable", context, policy)
    assert avail.status == "not_applicable"
    assert "art-h2" not in avail.matched_artifact_ids


def test_unknown_action_raises() -> None:
    registry = _registry()
    matcher = AvailabilityMatcher(registry)
    context = _context()
    policy = _policy()
    try:
        matcher.evaluate("contract.does-not-exist", context, policy)
    except Exception as exc:
        assert type(exc).__name__ == "NotFoundError"
    else:  # pragma: no cover
        raise AssertionError("expected NotFoundError for unknown action")


def test_disabled_pack_is_not_applicable() -> None:
    registry = _registry()
    registry.disable_pack("contract-pack")
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"})
    policy = _policy()
    avail = matcher.evaluate("contract.available", context, policy)
    assert avail.status == "not_applicable"
    assert any("pack" in r.lower() for r in avail.reasons)
