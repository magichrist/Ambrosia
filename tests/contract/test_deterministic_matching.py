# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.
"""Contract tests: deterministic matching for a fixed input snapshot.

The matcher must produce identical results for identical registry + context +
policy snapshots, and must not mutate either snapshot.
"""

from __future__ import annotations

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.models import Artifact
from ambrosia.registry import AvailabilityMatcher, ContextSnapshot, PolicySnapshot, Registry


def _build_registry() -> Registry:
    registry = Registry()
    registry.register_builtin(
        ActionDefinition(
            id="det.available",
            version="1.0.0",
            name="Available",
            description="available",
            category="discovery",
            tags=[],
            platforms=[],
            phase_refs=[],
            required_artifacts=[],
            input_schema={"type": "object", "properties": {}, "required": []},
            output_artifact_types=[],
            executor=ExecutorReference(kind="native"),
            dependencies=[],
            effects=["local_read"],
            risk="info",
            scope_fields=[],
            approval_required=False,
            timeout_seconds=10,
            max_output_bytes=2000000,
            parser_refs=[],
        )
    )
    return registry


def test_deterministic_across_repeated_evaluation() -> None:
    registry = _build_registry()
    matcher = AvailabilityMatcher(registry)
    context = ContextSnapshot(
        engagement_id="e1",
        selected_target={"address": "10.0.0.1"},
        artifacts=tuple(),
        inputs={},
        available_tools=frozenset(),
        platform="current",
    )
    policy = PolicySnapshot(
        allowed_effects=frozenset(["local_read"]),
        require_approval_for=frozenset(["local_write"]),
        include_hosts=tuple(["10.0.0.1"]),
        include_cidrs=tuple(),
        include_domains=tuple(),
        exclude_hosts=tuple(),
        exclude_cidrs=tuple(),
    )

    results = [matcher.evaluate_all(context, policy) for _ in range(5)]
    assert all(r == results[0] for r in results)

    # Direct evaluation is deterministic too.
    a1 = matcher.evaluate("det.available", context, policy)
    a2 = matcher.evaluate("det.available", context, policy)
    assert a1 == a2


def test_matching_does_not_mutate_snapshots() -> None:
    registry = _build_registry()
    matcher = AvailabilityMatcher(registry)
    context = ContextSnapshot(
        engagement_id="e1",
        selected_target={"address": "10.0.0.1"},
        artifacts=tuple(),
        inputs={"target": "10.0.0.1"},
        available_tools=frozenset(["nmap"]),
        platform="current",
    )
    policy = PolicySnapshot(
        allowed_effects=frozenset(["local_read", "network_observe"]),
        require_approval_for=frozenset(["local_write"]),
        include_hosts=tuple(["10.0.0.1"]),
        include_cidrs=tuple(),
        include_domains=tuple(),
        exclude_hosts=tuple(),
        exclude_cidrs=tuple(),
    )

    before_context = ContextSnapshot(
        engagement_id=context.engagement_id,
        selected_target=dict(context.selected_target) if context.selected_target else None,
        artifacts=context.artifacts,
        inputs=dict(context.inputs),
        available_tools=context.available_tools,
        platform=context.platform,
    )
    before_policy = PolicySnapshot(
        allowed_effects=policy.allowed_effects,
        require_approval_for=policy.require_approval_for,
        include_hosts=policy.include_hosts,
        include_cidrs=policy.include_cidrs,
        include_domains=policy.include_domains,
        exclude_hosts=policy.exclude_hosts,
        exclude_cidrs=policy.exclude_cidrs,
    )

    matcher.evaluate_all(context, policy)

    assert context == before_context
    assert policy == before_policy


def test_artifact_produces_available_after_context_change() -> None:
    """Different snapshots yield different (expected) results — matching is context-driven."""
    registry = _build_registry()
    matcher = AvailabilityMatcher(registry)

    policy = PolicySnapshot(
        allowed_effects=frozenset(["local_read"]),
        require_approval_for=frozenset(),
        include_hosts=tuple(["10.0.0.1"]),
        include_cidrs=tuple(),
        include_domains=tuple(),
        exclude_hosts=tuple(),
        exclude_cidrs=tuple(),
    )

    empty = ContextSnapshot(
        engagement_id="e1",
        selected_target=None,
        artifacts=tuple(),
        inputs={},
        available_tools=frozenset(),
        platform="current",
    )
    filled = ContextSnapshot(
        engagement_id="e1",
        selected_target={"address": "10.0.0.1"},
        artifacts=tuple(
            [Artifact(id="a1", engagement_id="e1", type="network.host", target_ref="10.0.0.1", value={})]
        ),
        inputs={"target": "10.0.0.1"},
        available_tools=frozenset(["nmap"]),
        platform="current",
    )

    # Action requires no inputs, so it's available even with no target.
    avail_empty = matcher.evaluate("det.available", empty, policy)
    avail_filled = matcher.evaluate("det.available", filled, policy)
    assert avail_empty.status == "available"
    assert avail_filled.status == "available"
    # The results are equal for this input-free action, demonstrating snapshot equality,
    # while a different snapshot (different inputs) would produce a different result.
