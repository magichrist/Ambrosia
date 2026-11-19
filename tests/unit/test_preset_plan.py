# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for preset plan construction (DAG validation and ordering)."""

from __future__ import annotations

from ambrosia.domain.action import ActionDefinition, ExecutorReference
from ambrosia.domain.preset import (
    PresetDefinition,
    PresetInput,
    PresetMetadata,
    PresetStep,
)
from ambrosia.presets.errors import (
    CyclicDependencyError,
    DuplicateStepIdError,
    InvalidPredicateError,
    InvalidReferenceError,
    UnresolvedActionError,
)
from ambrosia.presets.plan import build_plan
from ambrosia.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registry.register_builtin(
        ActionDefinition(
            id="net.discover",
            version="1.0.0",
            name="Discover",
            description="d",
            category="discovery",
            executor=ExecutorReference(kind="native"),
            effects=["network_observe"],
            input_schema={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
        )
    )
    registry.register_builtin(
        ActionDefinition(
            id="net.read",
            version="1.0.0",
            name="Read",
            description="d",
            category="inventory",
            executor=ExecutorReference(kind="native"),
            effects=["local_read"],
        )
    )
    return registry


def _preset(steps: list[PresetStep]) -> PresetDefinition:
    return PresetDefinition(
        metadata=PresetMetadata(
            id="unit.demo", name="Demo", version="1.0.0", description="d"
        ),
        inputs={"target": PresetInput(type="target.host", required=True)},
        steps=steps,
    )


def _step(
    step_id: str,
    *,
    type: str = "action",
    action: str | None = "net.discover",
    needs: list[str] | None = None,
    when: dict[str, object] | None = None,
    inputs: dict[str, object] | None = None,
    outputs: dict[str, object] | None = None,
    on_failure: str = "stop",
) -> PresetStep:
    return PresetStep(
        id=step_id,
        type=type,  # type: ignore[arg-type]
        action=action,
        needs=needs or [],
        when=when,
        inputs=inputs or {},
        outputs=outputs or {},
        on_failure=on_failure,  # type: ignore[arg-type]
    )


def test_duplicate_step_ids_rejected() -> None:
    preset = _preset([_step("a"), _step("a")])
    try:
        build_plan(preset, _registry())
    except DuplicateStepIdError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_cyclic_dependency_rejected() -> None:
    preset = _preset([_step("a", needs=["b"]), _step("b", needs=["a"])])
    try:
        build_plan(preset, _registry())
    except CyclicDependencyError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_self_dependency_via_output_reference_is_cycle() -> None:
    preset = _preset(
        [_step("a", inputs={"x": "{{ steps.a.outputs.y }}"}, outputs={"y": {"source": "{{ steps.a.outputs.x }}"}})]
    )
    try:
        build_plan(preset, _registry())
    except CyclicDependencyError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_unresolved_action_rejected() -> None:
    preset = _preset([_step("a", action="net.missing")])
    try:
        build_plan(preset, _registry())
    except UnresolvedActionError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_condition_without_predicate_rejected() -> None:
    preset = _preset([_step("c", type="condition", action=None, when=None)])
    try:
        build_plan(preset, _registry())
    except InvalidPredicateError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_non_action_step_rejects_action() -> None:
    preset = _preset([_step("c", type="condition", action="net.discover", when={"kind": "input_present", "input": "target"})])
    try:
        build_plan(preset, _registry())
    except InvalidReferenceError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_unknown_needs_rejected() -> None:
    preset = _preset([_step("a", needs=["missing"])])
    try:
        build_plan(preset, _registry())
    except InvalidReferenceError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_topological_order_deterministic_and_tie_broken_by_declaration() -> None:
    # Declare d, c, b, a with d -> b -> a. Declaration order breaks ties.
    preset = _preset(
        [
            _step("d", needs=["b"]),
            _step("c"),
            _step("b", needs=["a"]),
            _step("a"),
        ]
    )
    plan = build_plan(preset, _registry())
    again = build_plan(preset, _registry())
    assert plan.order == again.order
    assert plan.order == ("c", "a", "b", "d")


def test_implicit_dependency_from_output_reference() -> None:
    preset = _preset(
        [
            _step("c", inputs={"x": "{{ steps.a.outputs.y }}"}),
            _step("a"),
        ]
    )
    plan = build_plan(preset, _registry())
    assert plan.order.index("a") < plan.order.index("c")
    assert "a" in plan.steps["c"].needs


def test_effects_union() -> None:
    preset = _preset([_step("a"), _step("b", action="net.read")])
    plan = build_plan(preset, _registry())
    assert plan.effects == frozenset({"network_observe", "local_read"})


def test_required_inputs() -> None:
    preset = PresetDefinition(
        metadata=PresetMetadata(
            id="unit.demo", name="Demo", version="1.0.0", description="d"
        ),
        inputs={
            "required_one": PresetInput(type="string", required=True),
            "with_default": PresetInput(type="string", required=True, default="x"),
            "optional": PresetInput(type="string", required=False),
        },
        steps=[_step("a")],
    )
    plan = build_plan(preset, _registry())
    assert plan.required_inputs == ("required_one",)


def test_condition_branch_gating() -> None:
    preset = _preset(
        [
            _step(
                "cond",
                type="condition",
                action=None,
                when={"kind": "input_present", "input": "target"},
            ),
            _step("then_step"),
            _step("else_step"),
        ]
    )
    plan = build_plan(
        preset,
        _registry(),
        branches={"cond": (("then_step",), ("else_step",))},
    )
    cond = plan.steps["cond"]
    assert cond.then == ("then_step",)
    assert cond.else_ == ("else_step",)
    assert plan.steps["then_step"].gated_by == "cond"
    assert plan.steps["else_step"].gated_by == "cond"
    # Branch steps depend on the condition.
    assert "cond" in plan.steps["then_step"].needs
    assert "cond" in plan.steps["else_step"].needs


def test_branch_to_unknown_step_rejected() -> None:
    preset = _preset(
        [
            _step("cond", type="condition", action=None, when={"kind": "input_present", "input": "target"}),
        ]
    )
    try:
        build_plan(
            preset,
            _registry(),
            branches={"cond": (("missing",), ())},
        )
    except InvalidReferenceError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError()


def test_empty_preset_is_valid() -> None:
    preset = _preset([])
    plan = build_plan(preset, _registry())
    assert plan.order == ()
    assert plan.effects == frozenset()
