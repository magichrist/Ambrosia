# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the action-availability matcher (all statuses, determinism)."""

from __future__ import annotations

from ambrosia.domain.models import Artifact
from ambrosia.registry import (
    ActionAvailability,
    AvailabilityMatcher,
    ContextSnapshot,
    PolicySnapshot,
    Registry,
)


def _registry_with_pack() -> Registry:
    registry = Registry()
    import yaml

    pack_text = """
api_version: ambrosia/v1
kind: pack
metadata:
  id: matcher-pack
  name: Matcher Pack
  version: 1.0.0
  description: matcher fixture pack
actions:
  - id: match.available
    version: 1.0.0
    name: Available
    description: fully satisfied
    category: discovery
    tags: []
    platforms: []
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: native
    effects: [local_read]
    risk: info
    scope_fields: []
    approval_required: false
  - id: match.needs_input
    version: 1.0.0
    name: Needs Input
    description: missing a required input
    category: discovery
    tags: []
    platforms: []
    input_schema:
      type: object
      properties:
        target:
          type: string
      required: [target]
    executor:
      kind: native
    effects: [local_read]
    risk: info
    scope_fields: [target]
    approval_required: false
  - id: match.blocked_scope
    version: 1.0.0
    name: Blocked Scope
    description: target outside scope
    category: discovery
    tags: []
    platforms: []
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: native
    effects: [local_read]
    risk: info
    scope_fields: [target]
    approval_required: false
  - id: match.missing_dep
    version: 1.0.0
    name: Missing Dependency
    description: requires an absent tool
    category: discovery
    tags: []
    platforms: []
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: process
      executable: nonexistent-tool
    dependencies:
      - name: nonexistent-tool
    effects: [local_read]
    risk: info
    scope_fields: []
    approval_required: false
  - id: match.needs_approval
    version: 1.0.0
    name: Needs Approval
    description: requires approval
    category: inventory
    tags: []
    platforms: []
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: native
    effects: [local_write]
    risk: moderate
    scope_fields: []
    approval_required: true
  - id: match.not_applicable
    version: 1.0.0
    name: Not Applicable
    description: requires an absent artifact
    category: discovery
    tags: []
    platforms: []
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: native
    effects: [local_read]
    risk: info
    required_artifacts:
      - type: network.service
        same_target: true
    scope_fields: []
    approval_required: false
  - id: match.platform_only
    version: 1.0.0
    name: Platform Only
    description: windows-only platform
    category: discovery
    tags: []
    platforms: [windows]
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: native
    effects: [local_read]
    risk: info
    scope_fields: []
    approval_required: false
"""
    data = yaml.safe_load(pack_text)
    registry.load_pack(data)
    return registry


def _context(
    *,
    engagement_id="e1",
    selected_target=None,
    artifacts=(),
    inputs=None,
    available_tools=(),
    platform="current",
) -> ContextSnapshot:
    return ContextSnapshot(
        engagement_id=engagement_id,
        selected_target=selected_target,
        artifacts=tuple(artifacts),
        inputs=dict(inputs or {}),
        available_tools=frozenset(available_tools),
        platform=platform,
    )


def _policy(
    *,
    allowed_effects=("local_read", "network_observe", "local_write"),
    require_approval_for=("local_write", "remote_change", "authentication"),
    include_hosts=("10.0.0.1",),
    include_cidrs=(),
    include_domains=(),
    exclude_hosts=(),
    exclude_cidrs=(),
) -> PolicySnapshot:
    return PolicySnapshot(
        allowed_effects=frozenset(allowed_effects),
        require_approval_for=frozenset(require_approval_for),
        include_hosts=tuple(include_hosts),
        include_cidrs=tuple(include_cidrs),
        include_domains=tuple(include_domains),
        exclude_hosts=tuple(exclude_hosts),
        exclude_cidrs=tuple(exclude_cidrs),
    )


def _artifact(artifact_id, type_, target_ref=None, value=None) -> Artifact:
    return Artifact(
        id=artifact_id,
        engagement_id="e1",
        type=type_,
        target_ref=target_ref,
        value=dict(value or {}),
    )


def test_available_status() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, available_tools=())
    policy = _policy()
    avail = matcher.evaluate("match.available", context, policy)
    assert avail.status == "available"
    assert avail.reasons == []
    assert avail.missing_inputs == []
    assert avail.required_approval is False


def test_needs_input_status() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, inputs={}, available_tools=())
    policy = _policy()
    avail = matcher.evaluate("match.needs_input", context, policy)
    assert avail.status == "needs_input"
    assert "target" in avail.missing_inputs
    assert any("missing required input" in r for r in avail.reasons)


def test_blocked_scope_status() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "99.99.99.99"}, available_tools=())
    policy = _policy(include_hosts=("10.0.0.1",))
    avail = matcher.evaluate("match.blocked_scope", context, policy)
    assert avail.status == "blocked"
    assert any("blocked by scope" in r for r in avail.reasons)


def test_missing_dependency_status() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, available_tools=())
    policy = _policy()
    avail = matcher.evaluate("match.missing_dep", context, policy)
    assert avail.status == "missing_dependency"
    assert any("missing dependency: nonexistent-tool" in r for r in avail.reasons)


def test_needs_approval_status() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, available_tools=())
    policy = _policy()
    avail = matcher.evaluate("match.needs_approval", context, policy)
    assert avail.status == "needs_approval"
    assert avail.required_approval is True
    assert any("approval" in r.lower() for r in avail.reasons)


def test_not_applicable_missing_artifact() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, artifacts=(), available_tools=())
    policy = _policy()
    avail = matcher.evaluate("match.not_applicable", context, policy)
    assert avail.status == "not_applicable"
    assert any("missing required artifact: network.service" in r for r in avail.reasons)


def test_not_applicable_platform() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(
        selected_target={"address": "10.0.0.1"}, available_tools=(), platform="linux"
    )
    policy = _policy()
    avail = matcher.evaluate("match.platform_only", context, policy)
    assert avail.status == "not_applicable"
    assert any("platform" in r for r in avail.reasons)


def test_matched_artifact_ids_populated() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    artifact = _artifact(
        "art-1", "network.service", target_ref="10.0.0.1", value={"service": "smb"}
    )
    context = _context(
        selected_target={"address": "10.0.0.1"}, artifacts=(artifact,), available_tools=()
    )
    policy = _policy()
    # match.not_applicable requires network.service same_target -> now satisfied
    avail = matcher.evaluate("match.not_applicable", context, policy)
    assert "art-1" in avail.matched_artifact_ids
    assert avail.status == "available"


def test_target_scoped_artifact_does_not_match_other_target() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    artifact = _artifact(
        "art-1", "network.service", target_ref="10.0.0.2", value={"service": "smb"}
    )
    context = _context(
        selected_target={"address": "10.0.0.1"}, artifacts=(artifact,), available_tools=()
    )
    policy = _policy()
    avail = matcher.evaluate("match.not_applicable", context, policy)
    assert avail.status == "not_applicable"
    assert "art-1" not in avail.matched_artifact_ids
    assert any("missing required artifact: network.service" in r for r in avail.reasons)


def test_deterministic_matching() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, available_tools=())
    policy = _policy()
    first = matcher.evaluate_all(context, policy)
    second = matcher.evaluate_all(context, policy)
    assert first == second
    # Same snapshot, repeated calls, identical results.
    a1 = matcher.evaluate("match.available", context, policy)
    a2 = matcher.evaluate("match.available", context, policy)
    assert a1 == a2


def test_phase_refs_do_not_control_eligibility() -> None:
    registry = Registry()
    import yaml

    pack_text = """
api_version: ambrosia/v1
kind: pack
metadata:
  id: phase-pack
  name: Phase Pack
  version: 1.0.0
  description: phase metadata test
actions:
  - id: phase.foo
    version: 1.0.0
    name: Foo
    description: belongs to after-auth phase
    category: discovery
    tags: []
    platforms: []
    phase_refs: [after-auth]
    input_schema:
      type: object
      properties: {}
      required: []
    executor:
      kind: native
    effects: [local_read]
    risk: info
    scope_fields: []
    approval_required: false
"""
    data = yaml.safe_load(pack_text)
    registry.load_pack(data)
    matcher = AvailabilityMatcher(registry)
    context = _context(selected_target={"address": "10.0.0.1"}, available_tools=())
    policy = _policy()
    # No phase state is supplied at all; the action is still available.
    avail = matcher.evaluate("phase.foo", context, policy)
    assert avail.status == "available"


def test_all_statuses_covered() -> None:
    registry = _registry_with_pack()
    matcher = AvailabilityMatcher(registry)

    def make_context(*, selected_target=None, inputs=None, artifacts=(), available_tools=()):
        return _context(
            selected_target=selected_target,
            inputs=inputs,
            artifacts=artifacts,
            available_tools=available_tools,
        )

    cases = [
        ("match.available", make_context(selected_target={"address": "10.0.0.1"}), "available"),
        (
            "match.needs_input",
            make_context(selected_target={"address": "10.0.0.1"}, inputs={}),
            "needs_input",
        ),
        (
            "match.blocked_scope",
            make_context(selected_target={"address": "99.99.99.99"}),
            "blocked",
        ),
        (
            "match.missing_dep",
            make_context(selected_target={"address": "10.0.0.1"}),
            "missing_dependency",
        ),
        (
            "match.needs_approval",
            make_context(selected_target={"address": "10.0.0.1"}),
            "needs_approval",
        ),
        (
            "match.not_applicable",
            make_context(selected_target={"address": "10.0.0.1"}, artifacts=()),
            "not_applicable",
        ),
    ]
    for action_id, context, expected in cases:
        avail = matcher.evaluate(action_id, context, _policy())
        assert avail.status == expected, f"{action_id}: expected {expected}, got {avail.status}"
        assert isinstance(avail, ActionAvailability)
